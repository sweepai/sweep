import { Input } from "../ui/input";
import { ResizablePanel } from "../ui/resizable";
import { Textarea } from "../ui/textarea";
import React, { useEffect, useState } from "react";
import { Button } from "../ui/button";
import getFiles, { getFile, runScript, writeFile } from "../../lib/api.service";
import { toast } from "sonner";
import { FaCheck, FaPen, FaPlay, FaTrash } from "react-icons/fa6";
import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { FaArrowsRotate } from "react-icons/fa6";
import { CaretSortIcon } from "@radix-ui/react-icons";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { Snippet } from "../../lib/search";
import DashboardInstructions from "./DashboardInstructions";
import { FileChangeRequest } from "../../lib/types";

const DashboardActions = ({
  filePath,
  setScriptOutput,
  file,
  setFile,
  fileLimit,
  setFileLimit,
  blockedGlobs,
  setBlockedGlobs,
  hideMerge,
  setHideMerge,
  branch,
  setBranch,
  oldFile,
  setOldFile,
  repoName,
  setRepoName,
  setStreamData,
  files,
  fileChangeRequests,
  setFileChangeRequests,
  currentFileChangeRequestIndex,
  setCurrentFileChangeRequestIndex,
  setHideMergeAll,
  setFileByIndex,
  setOldFileByIndex,
}: any) => {
  const [script, setScript] = useLocalStorage("script", "python $FILE_PATH");
//   const [instructions, setInstructions] = useLocalStorage("instructions", "");
  const [isLoading, setIsLoading] = useState(false);
  const [currentRepoName, setCurrentRepoName] = useState(repoName);
  const [open, setOpen] = useState(false);
  const [repoNameCollapsibleOpen, setRepoNameCollapsibleOpen] = useLocalStorage("repoNameCollapsibleOpen",repoName === "");
  const [validationScriptCollapsibleOpen, setValidationScriptCollapsibleOpen] = useLocalStorage("validationScriptCollapsibleOpen",true);
  const [snippets, setSnippets] = useLocalStorage(
    "snippets",
    {} as { [key: string]: Snippet },
  );
  //console.log("file in DashboardActions.tsx", file)
  const instructions = (fileChangeRequests[currentFileChangeRequestIndex] as FileChangeRequest)?.instructions;
  const setInstructions = (instructions: string) => {
    setFileChangeRequests((prev: FileChangeRequest[]) => {
      return prev.map((fileChangeRequest: FileChangeRequest, index: number) => {
        if (index === currentFileChangeRequestIndex) {
          return {
            ...fileChangeRequest,
            instructions: instructions,
          };
        }
        return fileChangeRequest;
      });
    });
  }
  useEffect(() => {
    (async () => {
      const params = new URLSearchParams({ repo: repoName }).toString();
      const response = await fetch("/api/branch?" + params);
      const object = await response.json();
      setBranch(object.branch);
    })();
    if (repoName === "") {
      setRepoNameCollapsibleOpen(true);
    }
  }, [repoName]);

  const updateScript = (event: any) => {
    setScript(event.target.value);
  };
  const updateInstructons = (event: any) => {
    setInstructions(event.target.value);
  };
  const runScriptWrapper = async (newFile: string) => {
    const response = await runScript(repoName, filePath, script, newFile);
    const { code } = response;
    let scriptOutput = response.stdout + "\n" + response.stderr;
    if (code != 0) {
      scriptOutput = `Error (exit code ${code}):\n` + scriptOutput;
    }
    if (response.code != 0) {
      toast.error("An Error Occured", {
        description: [
          <div key="stdout">{response.stdout.slice(0, 800)}</div>,
          <div className="text-red-500" key="stderr">
            {response.stderr.slice(0, 800)}
          </div>,
        ],
      });
    } else {
      toast.success("The script ran successfully", {
        description: [
          <div key="stdout">{response.stdout.slice(0, 800)}</div>,
          <div key="stderr">{response.stderr.slice(0, 800)}</div>,
        ],
      });
    }
    setScriptOutput(scriptOutput);
  };

  const softIndentationCheck = (
    oldCode: string,
    newCode: string,
    fileContents: string,
  ): [string, string] => {
    let newOldCode = oldCode;
    let newNewCode = newCode;
    if (oldCode[0] === "\n") {
      // expect there to be a newline at the beginning of oldCode
      // find correct indentaton - try up to 16 spaces (8 indentations worth)
      for (let i of [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]) {
        // split new code by \n and add the same indentation to each line, then rejoin with new lines
        newOldCode =
          "\n" +
          oldCode
            .split("\n")
            .slice(1)
            .map((line) => " ".repeat(i) + line)
            .join("\n");
        if (fileContents.includes(newOldCode)) {
          newNewCode =
            "\n" +
            newCode
              .split("\n")
              .slice(1)
              .map((line) => " ".repeat(i) + line)
              .join("\n");
          break;
        }
      }
    }
    return [newOldCode, newNewCode];
  };

  const parseRegexFromOpenAI = (response: string, fileContents: string) => {
    const diffRegex =
      /<<<<<<< ORIGINAL(\n*?)(?<oldCode>.*?)(\n*?)=======(\n*?)(?<newCode>.*?)(\n*?)>>>>>>> MODIFIED/gs;
    const diffMatches: any = response.matchAll(diffRegex)!;
    if (!diffMatches) {
      return "";
    }
    var currentFileContents = fileContents;
    for (const diffMatch of diffMatches) {
      let oldCode = diffMatch.groups!.oldCode;
      let newCode = diffMatch.groups!.newCode;
      // soft match indentation, there are cases where openAi will miss indentations
      if (!currentFileContents.includes(oldCode)) {
        const [newOldCode, newNewCode]: [string, string] = softIndentationCheck(
          oldCode,
          newCode,
          currentFileContents,
        );
        currentFileContents = currentFileContents.replace(
          newOldCode,
          newNewCode,
        );
      } else {
        currentFileContents = currentFileContents.replace(oldCode, newCode);
      }
    }
    return currentFileContents;
  };

  const getFileChanges = async (fcr: FileChangeRequest, index: number) => {
    console.log("getting file changes")
    setStreamData("");
    // case where we are showing mergediff
    if (!hideMerge) {
      setFileChangeRequests((prev: FileChangeRequest[]) => {
        setHideMerge(true, index);
        setFileByIndex(prev[index].snippet.entireFile, index);
        return prev
      })
    }

    setIsLoading(true);
    const url = "/api/openai/edit";
    const body = JSON.stringify({
      fileContents: fcr.snippet.content.replace(/\\n/g, "\\n"),
      prompt: fcr.instructions,
      snippets: Object.values(snippets), //THIS MIGHT NEEED TO CHANGE LATER IF WE HAVE SNIPPETS FOR CERTAIN FCRS
    });
    const response = fetch(url, {
      method: "POST",
      body: body,
    })
      .then(async (response) => {
        const reader = response.body!.getReader();
        const decoder = new TextDecoder("utf-8");
        let rawText = String.raw``;
        console.log("ran!")

        var i = 0;
        setHideMerge(false, index);
        while (true) {
          i += 1;
          var { done, value } = await reader?.read();
          // maybe we can slow this down what do you think?, like give it a second? between updates of the code?
          if (done) {
            console.log("STREAM IS FULLY READ");
            setIsLoading(false);
            const updatedFile = parseRegexFromOpenAI(rawText || "", fcr.snippet.entireFile)
            setFileByIndex(updatedFile, index);
            break;
          }
          const text = decoder.decode(value);
          rawText += text;
          setStreamData((prev: any) => prev + text);
          if (i % 3 == 0) {
            try {
              let updatedFile = parseRegexFromOpenAI(rawText, fcr.snippet.entireFile);
              setFileByIndex(updatedFile, index);
            } catch (e) {
              console.error(e)
            }
          }
        }
        setHideMerge(false, index);
        const changeCount = Math.abs(
          fcr.snippet.entireFile.split("\n").length - fcr.newContents.split("\n").length,
        );
        toast.success(`Successfully generated tests!`, {
          description: [
            <div key="stdout">{`There were ${changeCount} line changes made`}</div>,
          ],
        });

        // if (script) {
        //   runScriptWrapper(file); // file is incorrect it should be based off of fcr
        // } else {
        //   toast.warning("Your Script is empty and will not be run.");
        // }
      })
      .catch((e) => {
        toast.error("An error occured while generating your code.", {
          description: e,
        });
        setIsLoading(false);
        return;
      });
  };

  // this needs to be async but its sync right now, fix later
  const getAllFileChanges = async (fcrs: FileChangeRequest[]) => {
    for await (const [index, fcr] of fcrs.entries()) {
      await getFileChanges(fcr, index)
      setCurrentFileChangeRequestIndex(index);
    }
  }

  const saveAllFiles = async (fcrs: FileChangeRequest[]) => {
    for await (const [index, fcr] of fcrs.entries()) {
      setOldFileByIndex(fcr.newContents, index);
      setHideMerge(true, index);
      await writeFile(repoName, fcr.snippet.file, fcr.newContents);
    }
    toast.success(`Succesfully saved ${fcrs.length} files!`);
  }

  const syncAllFiles = async () => {
    fileChangeRequests.forEach(async (fcr: FileChangeRequest, index: number) => {
      const response = await getFile(repoName, fcr.snippet.file);
      setFileByIndex(response.contents, index);
      setOldFileByIndex(response.contents, index);
    })
  }
  return (
    <ResizablePanel defaultSize={25} className="p-6 h-[90vh]">
      <div className="flex flex-col h-full">
        <Collapsible
          defaultOpen={repoName === ""}
          open={repoNameCollapsibleOpen}
          className="border-2 rounded p-4"
        >
          <div className="flex flex-row justify-between items-center mb-2">
            <Label className="mb-0">Repository Settings&nbsp;&nbsp;</Label>
            <CollapsibleTrigger>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setRepoNameCollapsibleOpen((open) => !open)}
              >
                { !repoNameCollapsibleOpen ? 'Expand': 'Collapse'}&nbsp;&nbsp;
                <CaretSortIcon className="h-4 w-4" />
                <span className="sr-only">Toggle</span>
              </Button>
            </CollapsibleTrigger>
          </div>
          <CollapsibleContent>
            <Label className="mb-2">Repository Path</Label>
            <Input
              id="name"
              placeholder="/Users/sweep/path/to/repo"
              value={currentRepoName}
              className="col-span-4 w-full"
              onChange={(e) => setCurrentRepoName(e.target.value)}
              onBlur={async () => {
                try {
                  let newFiles = await getFiles(
                    currentRepoName,
                    blockedGlobs,
                    fileLimit,
                  );
                  toast.success(
                    "Successfully fetched files from the repository!",
                  );
                  setCurrentRepoName((currentRepoName: string) => {
                    setRepoName(currentRepoName);
                    return currentRepoName;
                  });
                } catch (e) {
                  console.error(e);
                  toast.error("An Error Occured", {
                    description: "Please enter a valid repository name.",
                  });
                }
              }}
            />
            <p className="text-sm text-muted-foreground mb-4">
              Absolute path to your repository.
            </p>
            <Label className="mb-2">Branch</Label>
            <Input
              className="mb-4"
              value={branch}
              onChange={(e) => {
                setBranch(e.target.value);
                // TODO: make this work
              }}
              placeholder="your-branch-here"
            />
            <Label className="mb-2">Blocked Keywords</Label>
            <Input
              className="mb-4"
              value={blockedGlobs}
              onChange={(e) => {
                setBlockedGlobs(e.target.value);
                // TODO: make this work
              }}
              placeholder="node_modules, .log, build"
            />
            <Label className="mb-2">File Limit</Label>
            <Input
              value={fileLimit}
              onChange={(e) => {
                setFileLimit(e.target.value);
              }}
              placeholder="10000"
              type="number"
            />
          </CollapsibleContent>
        </Collapsible>

        <DashboardInstructions
          filePath={filePath}
          repoName={repoName}
          setSnippets={setSnippets}
          open={open}
          setOpen={setOpen}
          files={files}
          instructions={instructions}
          setInstructions={setInstructions}
          fileChangeRequests={fileChangeRequests}
          setFileChangeRequests={setFileChangeRequests}
          currentFileChangeRequestIndex={currentFileChangeRequestIndex}
          setCurrentFileChangeRequestIndex={setCurrentFileChangeRequestIndex}
          setFileByIndex={setFileByIndex}
          setOldFileByIndex={setOldFileByIndex}
          setHideMerge={setHideMerge}
          getFileChanges={getFileChanges}
        />
        <div>
          {Object.keys(snippets).map((snippet: string, index: number) => (
            <div className="flex mb-2" key={snippet}>
              <p className="border rounded overflow-x-auto grow mr-2 whitespace-pre bg-zinc-900 p-2 align-items-center">
                {snippet}
              </p>
              <Button
                variant="secondary"
                className="bg-zinc-900"
                onClick={() => {
                  setSnippets((prev: { [key: string]: Snippet }) => {
                    delete prev[snippet];
                    return prev;
                  });
                }}
              >
                <FaTrash />
              </Button>
            </div>
          ))}
        </div>

        <Collapsible open={validationScriptCollapsibleOpen} className="border-2 rounded p-4">
          <div className="flex flex-row justify-between items-center mt-2 mb-2">
            <Label className="mb-0">Validation Script&nbsp;&nbsp;</Label>
            <CollapsibleTrigger>
              <Button variant="secondary" size="sm" onClick={() => setValidationScriptCollapsibleOpen((open) => !open)}>
                { !validationScriptCollapsibleOpen ? 'Expand' : 'Collapse' }&nbsp;&nbsp;
                <CaretSortIcon className="h-4 w-4" />
                <span className="sr-only">Toggle</span>
              </Button>
            </CollapsibleTrigger>
            <div className="grow"></div>
            <Button
              variant="secondary"
              onClick={async () => {
                setIsLoading(true);
                await runScriptWrapper(file);
                setIsLoading(false);
              }}
              disabled={isLoading || !script.length}
              size="sm"
            >
              <FaPlay />
              &nbsp;&nbsp;Run Tests
            </Button>
          </div>
          <CollapsibleContent>
            <Textarea
              id="script-input"
              placeholder="Enter your script here"
              className="col-span-4 w-full font-mono height-fit-content"
              value={script}
              onChange={updateScript}
            ></Textarea>
            <p className="text-sm text-muted-foreground mb-4">
              Use $FILE_PATH to refer to the file you selected. E.g. `python
              $FILE_PATH`.
            </p>
          </CollapsibleContent>
        </Collapsible>
        <div className="flex flex-row justify-center">
          <Button
            className="mt-4 mr-4"
            variant="secondary"
            onClick={(e) => {
              getAllFileChanges(fileChangeRequests);
            }}
            disabled={isLoading}
          >
            <FaPlay />
            &nbsp;&nbsp;Modify All
          </Button>
          <Button
            className="mt-4 mr-4"
            variant="secondary"
            onClick={async () => {
              setIsLoading(true);
              syncAllFiles();
              toast.success("Files synced from storage!");
              setIsLoading(false);
              setHideMergeAll(true);
            }}
            disabled={isLoading}
          >
            <FaArrowsRotate />
            &nbsp;&nbsp;Restart All
          </Button>
          <Button
            className="mt-4 mr-2 bg-green-600 hover:bg-green-700"
            onClick={async () => {
              saveAllFiles(fileChangeRequests);
            }}
            disabled={isLoading || hideMerge}
          >
            <FaCheck />
            &nbsp;&nbsp;Save All
          </Button>
        </div>
      </div>
    </ResizablePanel>
  );
};

export default DashboardActions;
