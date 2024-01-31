import { Input } from "../ui/input";
import { ResizablePanel } from "../ui/resizable";
import { Textarea } from "../ui/textarea";
import React, { useEffect, useState } from "react";
import { Button } from "../ui/button";
import getFiles, { getFile, runScript, writeFile } from "../../lib/api.service";
import { toast } from "sonner";
import { FaCheck, FaPlay, FaTrash } from "react-icons/fa6";
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
import { FileChangeRequest, Message } from "../../lib/types";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "../ui/alert-dialog";
import { FaQuestion } from "react-icons/fa";
import { Switch } from "../ui/switch";

const systemMessagePrompt = `You are a brilliant and meticulous engineer assigned to modify a code file. When you write code, the code works on the first try and is syntactically perfect. You have the utmost care for the code that you write, so you do not make mistakes. Take into account the current code's language, code style and what the user is attempting to accomplish. You are to follow the instructions exactly and do nothing more. If the user requests multiple changes, you must make the changes one at a time and finish each change fully before moving onto the next change.

You MUST respond in the following diff format:

\`\`\`
<<<<<<< ORIGINAL
The first code block to replace. Ensure the indentation is valid.
=======
The new code block to replace the first code block. Ensure the indentation and syntax is valid.
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
The second code block to replace. Ensure the indentation is valid.
=======
The new code block to replace the second code block. Ensure the indentation and syntax is valid.
>>>>>>> MODIFIED
\`\`\`

You may write one or multiple diff hunks. The MODIFIED can be empty.`;

const userMessagePrompt = `Here are relevant read-only files:
<read_only_files>
{readOnlyFiles}
</read_only_files>

Here are the file's current contents:
<file_contents>
{fileContents}
</file_contents>

Your job is to modify the current code file in order to complete the user's request:
<user_request>
{prompt}
</user_request>`;

const readOnlyFileFormat = `<read_only_file file="{file}" start_line="{start_line}" end_line="{end_line}">
{contents}
</read_only_file>`;

const retryPrompt = `The following error occurred while generating the code:
<error_message>
{errorMessage}
</error_message>

Please try again by rewriting the diff hunks with corrections.`;

const formatUserMessage = (
  request: string,
  fileContents: string,
  snippets: Snippet[]
) => {
  return userMessagePrompt
    .replace("{prompt}", request)
    .replace("{fileContents}", fileContents)
    .replace(
      "{readOnlyFiles}",
      snippets
        .map((snippet) =>
          readOnlyFileFormat
            .replace("{file}", snippet.file)
            .replace("{start_line}", snippet.start.toString())
            .replace("{end_line}", snippet.end.toString())
            .replace("{contents}", snippet.content),
        )
        .join("\n"),
    )
};

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
  setIsLoading,
  setIsLoadingAll,
  undefinedCheck
}: {
  filePath: string;
  setScriptOutput: React.Dispatch<React.SetStateAction<string>>;
  file: string;
  setFile: (newFile: string) => void;
  fileLimit: number;
  setFileLimit: React.Dispatch<React.SetStateAction<number>>;
  blockedGlobs: string;
  setBlockedGlobs: React.Dispatch<React.SetStateAction<string>>;
  hideMerge: boolean;
  setHideMerge: (newHideMerge: boolean, index: number) => void;
  branch: string;
  setBranch: React.Dispatch<React.SetStateAction<string>>;
  oldFile: string;
  setOldFile: (newOldFile: string) => void;
  repoName: string;
  setRepoName: React.Dispatch<React.SetStateAction<string>>;
  setStreamData: React.Dispatch<React.SetStateAction<string>>;
  files: { label: string; name: string }[];
  fileChangeRequests: FileChangeRequest[];
  setFileChangeRequests: React.Dispatch<React.SetStateAction<FileChangeRequest[]>>;
  currentFileChangeRequestIndex: number;
  setCurrentFileChangeRequestIndex: React.Dispatch<React.SetStateAction<number>>;
  setHideMergeAll: (newHideMerge: boolean) => void;
  setFileByIndex: (newFile: string, index: number) => void;
  setOldFileByIndex: (newOldFile: string, index: number) => void;
  setIsLoading: (newIsLoading: boolean, index: number) => void;
  setIsLoadingAll: (newIsLoading: boolean) => void;
  undefinedCheck: (variable: any) => void;
}) => {
  const validationScriptPlaceholder = `Example: python3 -m py_compile $FILE_PATH\npython3 -m pylint $FILE_PATH --error-only`
  const testScriptPlaceholder = `Example: python3 -m pytest $FILE_PATH`
  const [validationScript, setValidationScript] = useLocalStorage("validationScript", "")
  const [testScript, setTestScript] = useLocalStorage("testScript", "");
  const [currentRepoName, setCurrentRepoName] = useState(repoName);
  const [open, setOpen] = useState(false);
  const [repoNameCollapsibleOpen, setRepoNameCollapsibleOpen] = useLocalStorage("repoNameCollapsibleOpen", repoName === "");
  const [validationScriptCollapsibleOpen, setValidationScriptCollapsibleOpen] = useLocalStorage("validationScriptCollapsibleOpen", false);
  const [doValidate, setDoValidate] = useLocalStorage("doValidation", true);
  // const [snippets, setSnippets] = useLocalStorage(
  //   "snippets",
  //   {} as { [key: string]: Snippet },
  // );
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
  
  // updates readOnlySnippets for a certain fcr then updates entire fileChangeRequests array
  const setReadOnlySnippetForFCR = (fcr: FileChangeRequest, readOnlySnippet: Snippet) => {
    try {
      fcr.readOnlySnippets[readOnlySnippet.file] = readOnlySnippet;
      const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) => fileChangeRequest.snippet.file === fcr.snippet.file);
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev: FileChangeRequest[]) => {
        return [
          ...prev.slice(0, fcrIndex),
          fcr,
          ...prev.slice(fcrIndex + 1)
        ]
      });
    } catch (error) {
      console.error("Error in setReadOnlySnippetForFCR: ",error);
    }
  }

  const removeReadOnlySnippetForFCR = (fcr: FileChangeRequest, snippetFile: string) => {
    try {
      delete fcr.readOnlySnippets[snippetFile];
      const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) => fileChangeRequest.snippet.file === fcr.snippet.file);
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev: FileChangeRequest[]) => {
        return [
          ...prev.slice(0, fcrIndex),
          fcr,
          ...prev.slice(fcrIndex + 1)
        ]
      });
    } catch (error) {
      console.error("Error in removeReadOnlySnippetForFCR: ",error);
    }
  }

  const setReadOnlyFilesOpen = (newOpen: boolean, fcr: FileChangeRequest, index: number | undefined = undefined) => {
    try {
      let fcrIndex = index;
      if (typeof index === "undefined") {
        fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) => fileChangeRequest.snippet.file === fcr.snippet.file);
      }
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev: FileChangeRequest[]) => {  
        return [
          ...prev.slice(0, fcrIndex),
          {
            ...prev[fcrIndex!],
            openReadOnlyFiles: newOpen
          },
          ...prev.slice(fcrIndex! + 1)
        ]
      })
    } catch (error) {
      console.error("Error in setReadOnlyFilesOpen: ",error);
    }
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

  const runScriptWrapper = async (newFile: string) => {
    const response = await runScript(repoName, filePath, validationScript + "\n" + testScript, newFile);
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
        action: { label: "Dismiss", onClick: () => { } }
      });
    } else {
      toast.success("The script ran successfully", {
        description: [
          <div key="stdout">{response.stdout.slice(0, 800)}</div>,
          <div key="stderr">{response.stderr.slice(0, 800)}</div>,
        ],
        action: { label: "Dismiss", onClick: () => { } }
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
    // expect there to be a newline at the beginning of oldCode
    // find correct indentaton - try up to 16 spaces (8 indentations worth)
    for (let i of [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]) {
      // split new code by \n and add the same indentation to each line, then rejoin with new lines
      newOldCode =
        "\n" +
        oldCode
          .split("\n")
          .map((line) => " ".repeat(i) + line)
          .join("\n");
      if (fileContents.includes(newOldCode)) {
        newNewCode =
          "\n" +
          newCode
            .split("\n")
            .map((line) => " ".repeat(i) + line)
            .join("\n");
        break;
      }
    }
    return [newOldCode, newNewCode];
  };

  const parseRegexFromOpenAI = (response: string, fileContents: string): [string, string] => {
    let errorMessage = "";
    const diffRegex =
      /<<<<<<< ORIGINAL(\n+?)(?<oldCode>.*?)(\n*?)=======(\n+?)(?<newCode>.*?)(\n*?)>>>>>>> MODIFIED/gs;
    const diffMatches: any = response.matchAll(diffRegex)!;
    if (!diffMatches) {
      return ["", ""];
    }
    var currentFileContents = fileContents;
    var changesMade = false;
    for (const diffMatch of diffMatches) {
      changesMade = true;
      let oldCode = diffMatch.groups!.oldCode;
      let newCode = diffMatch.groups!.newCode;
      let didFind = false;
      if (oldCode.startsWith("\n")) {
        oldCode = oldCode.slice(1);
      }
      // soft match indentation, there are cases where openAi will miss indentations
      if (oldCode.trim().length === 0) {
        errorMessage += "ORIGINAL code block can not be empty.\n\n";
        continue
      }
      // console.log(oldCode)
      // console.log(currentFileContents)
      // console.log(currentFileContents.includes(oldCode))
      if (!currentFileContents.includes(oldCode)) {
        const [newOldCode, newNewCode]: [string, string] = softIndentationCheck(
          oldCode,
          newCode,
          currentFileContents,
        );
        if (currentFileContents.includes(newOldCode)) {
          didFind = true;
        }
        currentFileContents = currentFileContents.replace(
          newOldCode,
          newNewCode,
        );
      } else {
        didFind = true;
        currentFileContents = currentFileContents.replace(oldCode, newCode);
      }
      if (!didFind) {
        errorMessage += `ORIGINAL code block not found in file:\n\`\`\`\n${oldCode}\n\`\`\`\n\n`;
      }
    }
    if (!changesMade) {
      errorMessage += "No diff hunks we're found in the response.\n\n";
    }
    return [currentFileContents, errorMessage];
  };

  const checkForErrors = async (filePath: string, oldFile: string, newFile: string) => {
    if (!doValidate) {
      return "";
    }
    const { stdout, stderr, code } = await runScript(repoName, filePath, validationScript, newFile);
    // TODO: add diff
    return code !== 0 ? stdout + "\n" + stderr: "";
  }

  const getFileChanges = async (fcr: FileChangeRequest, index: number) => {
    setStreamData("");
    // case where we are showing mergediff
    if (!hideMerge) {
      setFileChangeRequests((prev: FileChangeRequest[]) => {
        setHideMerge(true, index);
        setFileByIndex(prev[index].snippet.entireFile, index);
        return prev
      })
    }

    setIsLoading(true, index);
    const url = "/api/openai/edit";
    const body = {
      prompt: fcr.instructions,
      snippets: Object.values(fcr.readOnlySnippets),
    };
    const additionalMessages: Message[] = [];
    var currentContents = fcr.snippet.entireFile.replace(/\\n/g, "\\n");
    let errorMessage = ""
    let userMessage = formatUserMessage(
      fcr.instructions,
      currentContents,
      Object.values(fcr.readOnlySnippets)
    )
    for (let i = 0; i < 3; i++) {
      userMessage = i === 0 ? userMessage : retryPrompt.replace("{errorMessage}", errorMessage.trim())
      const response = await fetch(url, {
        method: "POST",
        body: JSON.stringify({
          ...body,
          fileContents: currentContents,
          additionalMessages,
          userMessage: (
            i === 0 ? userMessage : retryPrompt.replace("{errorMessage}", errorMessage.trim())
          ),
        }),
      })
      additionalMessages.push({ role: "user", content: userMessage });
      errorMessage = ""
      try {
        const reader = response.body!.getReader();
        const decoder = new TextDecoder("utf-8");
        let rawText = String.raw``;

        setHideMerge(false, index);
        while (true) {
          var { done, value } = await reader?.read();
          // maybe we can slow this down what do you think?, like give it a second? between updates of the code?
          if (done) {
            const [updatedFile, patchingErrors] = parseRegexFromOpenAI(rawText || "", currentContents)
            // console.log(patchingErrors)
            if (patchingErrors) {
              errorMessage += patchingErrors;
            } else {
              errorMessage += await checkForErrors(fcr.snippet.file, fcr.snippet.entireFile, updatedFile);
            }
            additionalMessages.push({ role: "assistant", content: rawText });
            setFileByIndex(updatedFile, index);
            fcr.newContents = updatedFile // set this to get line and char changes
            rawText += "\n\n"
            break;
          }
          const text = decoder.decode(value);
          rawText += text;
          setStreamData((prev: string) => prev + text);
          if (i % 3 == 0) {
            try {
              let [updatedFile, _] = parseRegexFromOpenAI(rawText, fcr.snippet.entireFile);
              setFileByIndex(updatedFile, index);
            } catch (e) {
              console.error(e)
            }
          }
        }
        setHideMerge(false, index);
        const changeLineCount = Math.abs(
          fcr.snippet.entireFile.split("\n").length - fcr.newContents.split("\n").length
        );
        const changeCharCount = Math.abs(
          fcr.snippet.entireFile.length - fcr.newContents.length
        )
        if (errorMessage.length > 0) {
          toast.error("An error occured while generating your code." + (i < 2 ? " Retrying...": " Retried 3 times so I will give up."), {
            description: errorMessage,
          });
          continue
        } else {
          toast.success(`Successfully modified file!`, {
            description: [
              <div key="stdout">{`There were ${changeLineCount} line and ${changeCharCount} character changes made.`}</div>,
            ],
            action: { label: "Dismiss", onClick: () => { } }
          });
          setIsLoading(false, index);
          break
        }
      } catch (e: any) {
        toast.error("An error occured while generating your code.", {
          description: e, action: { label: "Dismiss", onClick: () => { } }
        });
        setIsLoading(false, index);
      }
    }
    setIsLoading(false, index);
  };

  // this needs to be async but its sync right now, fix later
  const getAllFileChanges = async (fcrs: FileChangeRequest[]) => {
    for (let index = 0; index < fcrs.length; index++) {
      await getFileChanges(fcrs[index], index)
    }
  }

  const saveAllFiles = async (fcrs: FileChangeRequest[]) => {
    for await (const [index, fcr] of fcrs.entries()) {
      setOldFileByIndex(fcr.newContents, index);
      setHideMerge(true, index);
      await writeFile(repoName, fcr.snippet.file, fcr.newContents);
    }
    toast.success(`Succesfully saved ${fcrs.length} files!`, { action: { label: "Dismiss", onClick: () => { } } });
  }

  const syncAllFiles = async () => {
    fileChangeRequests.forEach(async (fcr: FileChangeRequest, index: number) => {
      const response = await getFile(repoName, fcr.snippet.file);
      setFileByIndex(response.contents, index);
      setOldFileByIndex(response.contents, index);
      setIsLoading(false, index);
    })
  }
  return (
    <ResizablePanel defaultSize={35} className="p-6 h-[90vh]">
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
                {!repoNameCollapsibleOpen ? 'Expand' : 'Collapse'}&nbsp;&nbsp;
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
                    "Successfully fetched files from the repository!", { action: { label: "Dismiss", onClick: () => { } } }
                  );
                  setCurrentRepoName((currentRepoName: string) => {
                    setRepoName(currentRepoName);
                    return currentRepoName;
                  });
                } catch (e) {
                  console.error(e);
                  toast.error("An Error Occured", {
                    description: "Please enter a valid repository name.",
                    action: { label: "Dismiss", onClick: () => { } }
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
                setFileLimit(parseInt(e.target.value));
              }}
              placeholder="10000"
              type="number"
            />
          </CollapsibleContent>
        </Collapsible>

        <DashboardInstructions
          filePath={filePath}
          repoName={repoName}
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
          setReadOnlySnippetForFCR={setReadOnlySnippetForFCR}
          setReadOnlyFilesOpen={setReadOnlyFilesOpen}
          removeReadOnlySnippetForFCR={removeReadOnlySnippetForFCR}
        />

        <Collapsible open={validationScriptCollapsibleOpen} className="border-2 rounded p-4">
          <div className="flex flex-row justify-between items-center mt-2 mb-2">
            <Label className="mb-0 flex flex-row items-center">Checks&nbsp;
              <AlertDialog>
                <AlertDialogTrigger>
                  <Button variant="secondary" size="sm" className="rounded-lg ml-1 mr-2">
                    <FaQuestion style={{fontSize: 12 }} />
                  </Button>
                </AlertDialogTrigger>
                <Switch
                  checked={doValidate}
                  onClick={() => setDoValidate(!doValidate)}
                  disabled={fileChangeRequests.some((fcr: FileChangeRequest) => fcr.isLoading)}
                />
                <AlertDialogContent className="p-12">
                  <AlertDialogHeader>
                    <AlertDialogTitle className="text-5xl mb-2">
                      Test and Validation Scripts
                    </AlertDialogTitle>
                    <AlertDialogDescription className="text-md pt-4">
                      <p>
                        We highly recommend setting up the validation script to allow Sweep to iterate against static analysis tools to ensure the generated code is formatted and linted correctly. By default, Sweep will do this automatically but you have the ability to disable this check.
                      </p>
                      <h2 className="text-2xl mt-4 mb-2 text-zinc-100">
                        Validation Script
                      </h2>
                      <p>
                        The validation script is used to check the code generated by Sweep after every file edit. If it fails, Sweep will try to auto-fix it.
                        <br/>
                        We recommended running a syntax checker (a formatter suffices) followed by a linter. We also recommend using the same formatter and linter that you use in your local environment, to ensure all the dependencies are accounted for.
                        <br/>
                        For example, for Python you can use:
                        <pre className="py-4">
                          <code>
                            python -m py_compile $FILE_PATH
                            <br/>
                            pylint $FILE_PATH --error-only
                          </code>
                        </pre>
                        And for JavaScript you can use:
                        <pre className="py-4">
                          <code>
                            prettier $FILE_PATH
                            <br/>
                            eslint $FILE_PATH
                          </code>
                        </pre>
                      </p>
                      <h2 className="text-2xl mt-4 mb-2 text-zinc-100">
                        Test Script
                      </h2>
                      <p>
                        The test script is used to run tests after all the edits have been completed by Sweep. E.g.
                        For example, for Python you can use:
                        <pre className="py-4">
                          pytest $FILE_PATH
                        </pre>
                        And for JavaScript you can use:
                        <pre className="py-4">
                          jest $FILE_PATH
                        </pre>
                      </p>
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>
                      Close
                    </AlertDialogCancel>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </Label>
            <div className="grow"></div>
            <Button
              variant="secondary"
              onClick={async () => {
                await runScriptWrapper(file);
              }}
              disabled={fileChangeRequests.some((fcr: FileChangeRequest) => fcr.isLoading) || !doValidate}
              size="sm"
              className="mr-2"
            >
              <FaPlay />
              &nbsp;&nbsp;Run Tests
            </Button>
            <CollapsibleTrigger>
              <Button variant="secondary" size="sm" onClick={() => setValidationScriptCollapsibleOpen((open: boolean) => !open)}>
                { !validationScriptCollapsibleOpen ? 'Expand' : 'Collapse' }&nbsp;&nbsp;
                <CaretSortIcon className="h-4 w-4" />
                <span className="sr-only">Toggle</span>
              </Button>
            </CollapsibleTrigger>
          </div>
          <CollapsibleContent className="pt-2">
            <Label className="mb-0">
              Validation Script&nbsp;

            </Label>
            <Textarea
              id="script-input"
              placeholder={validationScriptPlaceholder}
              className="col-span-4 w-full font-mono height-fit-content"
              value={validationScript}
              onChange={(e) => setValidationScript(e.target.value)}
              disabled={fileChangeRequests.some((fcr: FileChangeRequest) => fcr.isLoading) || !doValidate}
            ></Textarea>
            <Label className="mb-0">Test Script</Label>
            <Textarea
              id="script-input"
              placeholder={testScriptPlaceholder}
              className="col-span-4 w-full font-mono height-fit-content"
              value={testScript}
              onChange={(e) => setTestScript(e.target.value)}
              disabled={fileChangeRequests.some((fcr: FileChangeRequest) => fcr.isLoading) || !doValidate}
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
            onClick={async (e) => {
              setIsLoadingAll(true);
              await getAllFileChanges(fileChangeRequests);
            }}
            disabled={fileChangeRequests.some((fcr: FileChangeRequest) => fcr.isLoading)}
          >
            <FaPlay />
            &nbsp;&nbsp;Modify All
          </Button>
          <Button
            className="mt-4 mr-4"
            variant="secondary"
            onClick={async () => {
              syncAllFiles();
              toast.success("Files synced from storage!", { action: { label: "Dismiss", onClick: () => { } } });
              setHideMergeAll(true);
            }}
            disabled={fileChangeRequests.some((fcr: FileChangeRequest) => fcr.isLoading)}
          >
            <FaArrowsRotate />
            &nbsp;&nbsp;Restart All
          </Button>
          <Button
            className="mt-4 mr-2 bg-green-600 hover:bg-green-700"
            onClick={async () => {
              saveAllFiles(fileChangeRequests);
            }}
            disabled={fileChangeRequests.some((fcr: FileChangeRequest) => fcr.isLoading)}
          >
            <FaCheck />
            &nbsp;&nbsp;Save
          </Button>
        </div>
      </div>
    </ResizablePanel>
  );
};

export default DashboardActions;
