"use client";

import { Input } from "../ui/input";
import { ResizablePanel } from "../ui/resizable";
import { Textarea } from "../ui/textarea";
import React, { useEffect, useRef, useState } from "react";
import { Button } from "../ui/button";
import getFiles, { getFile, runScript, writeFile } from "../../lib/api.service";
import { toast } from "sonner";
import { FaPlay } from "react-icons/fa6";
import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { CaretSortIcon } from "@radix-ui/react-icons";
import { Collapsible, CollapsibleContent } from "../ui/collapsible";
import { Snippet } from "../../lib/search";
import DashboardInstructions from "./DashboardInstructions";
import { FileChangeRequest, Message, fcrEqual } from "../../lib/types";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import { FaCog, FaQuestion } from "react-icons/fa";
import { Switch } from "../ui/switch";
import { usePostHog } from "posthog-js/react";
import { Dialog, DialogContent } from "../ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import DashboardPlanning from "./DashboardPlanning";
import { useRecoilState } from "recoil";
import { FileChangeRequestsState } from "../../state/fcrAtoms";
import {
  parseRegexFromOpenAICreate,
  parseRegexFromOpenAIModify,
} from "../../lib/patchUtils";
import {
  setIsLoading,
  setFileForFCR,
  setOldFileForFCR,
  setStatusForFCR,
  setDiffForFCR,
} from "../../state/fcrStateHelpers";

const Diff = require("diff");

const systemMessagePromptCreate = `You are creating a file of code in order to solve a user's request. You will follow the request under "# Request" and respond based on the format under "# Format".

# Request

file_name: "{filename}"

{instructions}`;

const changesMadePrompt = `The following changes have already been made as part of this task in unified diff format:

<changes_made>
{changesMade}
</changes_made>`;

const userMessagePromptCreate = `Here are relevant read-only files:
<read_only_files>
{readOnlyFiles}
</read_only_files>

Your job is to create a new code file in order to complete the user's request:
<user_request>
{prompt}
</user_request>`;

const userMessagePrompt = `Here are relevant read-only files:
<read_only_files>
{readOnlyFiles}
</read_only_files>

Here are the file's current contents:
<file_to_modify>
{fileContents}
</file_to_modify>

Your job is to modify the current code file in order to complete the user's request:
<user_request>
{prompt}
</user_request>`;

const readOnlyFileFormat = `<read_only_file file="{file}" start_line="{start_line}" end_line="{end_line}">
{contents}
</read_only_file>`;

const retryChangesMadePrompt = `The following error occurred while editing the code. The following changes have been made:
<changes_made>
{changes_made}
</changes_made>

However, the following error occurred while editing the code:
<error_message>
{error_message}
</error_message>

Please identify the error and how to correct the error. Then rewrite the diff hunks with the corrections to continue to modify the code.`;

const retryPrompt = `The following error occurred while generating the code:
<error_message>
{error_message}
</error_message>

Please identify the error and how to correct the error. Then rewrite the diff hunks with the corrections to continue to modify the code.`;

const createPatch = (filePath: string, oldFile: string, newFile: string) => {
  if (oldFile === newFile) {
    return "";
  }
  return Diff.createPatch(filePath, oldFile, newFile);
};

const formatUserMessage = (
  request: string,
  fileContents: string,
  snippets: Snippet[],
  patches: string,
  changeType: string,
) => {
  const patchesSection =
    patches.trim().length > 0
      ? changesMadePrompt.replace("{changesMade}", patches.trimEnd()) + "\n\n"
      : "";
  let basePrompt = userMessagePrompt;
  if (changeType == "create") {
    basePrompt = userMessagePromptCreate;
  }
  const userMessage =
    patchesSection +
    basePrompt
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
      );
  return userMessage;
};

const DashboardActions = ({
  filePath,
  setScriptOutput,
  file,
  fileLimit,
  setFileLimit,
  blockedGlobs,
  setBlockedGlobs,
  hideMerge,
  setHideMerge,
  repoName,
  setRepoName,
  setStreamData,
  files,
  directories,
  currentFileChangeRequestIndex,
  setCurrentFileChangeRequestIndex,
  setOutputToggle,
  setLoadingMessage,
}: {
  filePath: string;
  setScriptOutput: React.Dispatch<React.SetStateAction<string>>;
  file: string;
  fileLimit: number;
  setFileLimit: React.Dispatch<React.SetStateAction<number>>;
  blockedGlobs: string;
  setBlockedGlobs: React.Dispatch<React.SetStateAction<string>>;
  hideMerge: boolean;
  setHideMerge: (newHideMerge: boolean, fcr: FileChangeRequest) => void;
  repoName: string;
  setRepoName: React.Dispatch<React.SetStateAction<string>>;
  setStreamData: React.Dispatch<React.SetStateAction<string>>;
  files: { label: string; name: string }[];
  directories: { label: string; name: string }[];
  currentFileChangeRequestIndex: number;
  setCurrentFileChangeRequestIndex: React.Dispatch<
    React.SetStateAction<number>
  >;
  setOutputToggle: (newOutputToggle: string) => void;
  setLoadingMessage: React.Dispatch<React.SetStateAction<string>>;
}) => {
  const [fileChangeRequests, setFileChangeRequests] = useRecoilState(
    FileChangeRequestsState,
  );
  const posthog = usePostHog();
  const validationScriptPlaceholder = `Example: python3 -m py_compile $FILE_PATH\npython3 -m pylint $FILE_PATH --error-only`;
  const testScriptPlaceholder = `Example: python3 -m pytest $FILE_PATH`;
  const [validationScript, setValidationScript] = useLocalStorage(
    "validationScript",
    "",
  );
  const [testScript, setTestScript] = useLocalStorage("testScript", "");
  const [currentRepoName, setCurrentRepoName] = useState(repoName);
  const [currentBlockedGlobs, setCurrentBlockedGlobs] = useState(blockedGlobs);
  const [repoNameCollapsibleOpen, setRepoNameCollapsibleOpen] = useLocalStorage(
    "repoNameCollapsibleOpen",
    false,
  );
  const [validationScriptCollapsibleOpen, setValidationScriptCollapsibleOpen] =
    useLocalStorage("validationScriptCollapsibleOpen", false);
  const [doValidate, setDoValidate] = useLocalStorage("doValidation", true);
  const isRunningRef = useRef(false);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);

  const [currentTab = "coding", setCurrentTab] = useLocalStorage(
    "currentTab",
    "planning" as "planning" | "coding",
  );

  const refreshFiles = async () => {
    try {
      let { directories, sortedFiles } = await getFiles(
        currentRepoName,
        blockedGlobs,
        fileLimit,
      );
      if (sortedFiles.length === 0) {
        throw new Error("No files found in the repository");
      }
      toast.success(
        `Successfully fetched ${sortedFiles.length} files from the repository!`,
        { action: { label: "Dismiss", onClick: () => {} } },
      );
      setCurrentRepoName((currentRepoName: string) => {
        setRepoName(currentRepoName);
        return currentRepoName;
      });
    } catch (e) {
      console.error(e);
      toast.error("An Error Occured", {
        description: "Please enter a valid repository name.",
        action: { label: "Dismiss", onClick: () => {} },
      });
    }
  };

  useEffect(() => {
    setRepoNameCollapsibleOpen(repoName === "");
  }, [repoName]);

  useEffect(() => {
    if (repoName === "") {
      setRepoNameCollapsibleOpen(true);
    }
  }, [repoName]);

  const runScriptWrapper = async (newFile: string) => {
    const response = await runScript(
      repoName,
      filePath,
      validationScript + "\n" + testScript,
      newFile,
    );
    const { code } = response;
    let scriptOutput = response.stdout + "\n" + response.stderr;
    if (code != 0) {
      scriptOutput = `Error (exit code ${code}):\n` + scriptOutput;
    }
    if (response.code != 0) {
      toast.error("An Error Occured", {
        description: [
          <div key="stdout">{(response.stdout || "").slice(0, 800)}</div>,
          <div className="text-red-500" key="stderr">
            {(response.stderr || "").slice(0, 800)}
          </div>,
        ],
        action: { label: "Dismiss", onClick: () => {} },
      });
    } else {
      toast.success("The script ran successfully", {
        description: [
          <div key="stdout">{(response.stdout || "").slice(0, 800)}</div>,
          <div key="stderr">{(response.stderr || "").slice(0, 800)}</div>,
        ],
        action: { label: "Dismiss", onClick: () => {} },
      });
    }
    setScriptOutput(scriptOutput);
  };

  const checkCode = async (sourceCode: string, filePath: string) => {
    const response = await fetch(
      "/api/files/check?" +
        new URLSearchParams({ filePath, sourceCode }).toString(),
    );
    return await response.text();
  };

  const checkForErrors = async (
    filePath: string,
    oldFile: string,
    newFile: string,
  ) => {
    setLoadingMessage("Validating...");
    if (!doValidate) {
      return "";
    }
    const parsingErrorMessageOld = checkCode(oldFile, filePath);
    const parsingErrorMessage = checkCode(newFile, filePath);
    if (!parsingErrorMessageOld && parsingErrorMessage) {
      return parsingErrorMessage;
    }
    var { stdout, stderr, code } = await runScript(
      repoName,
      filePath,
      validationScript,
      oldFile,
    );
    var { stdout, stderr, code } = await runScript(
      repoName,
      filePath,
      validationScript,
      newFile,
    );
    // TODO: add diff
    setScriptOutput(stdout + "\n" + stderr);
    return code !== 0 ? stdout + "\n" + stderr : "";
  };

  // modify an existing file or create a new file
  const getFileChanges = async (fcr: FileChangeRequest, index: number) => {
    console.log("getting file changes")
    var validationOutput = "";
    const patches = fileChangeRequests
      .slice(0, index)
      .map((fcr: FileChangeRequest) => {
        return fcr.diff;
      })
      .join("\n\n");

    setIsLoading(true, fcr, fileChangeRequests, setFileChangeRequests);
    setStatusForFCR(
      "in-progress",
      fcr,
      fileChangeRequests,
      setFileChangeRequests,
    );
    setOutputToggle("llm");
    setLoadingMessage("Queued...");
    const changeType = fcr.changeType;
    // by default we modify file
    let url = "/api/openai/edit";
    let prompt = fcr.instructions;
    if (changeType === "create") {
      url = "/api/openai/create";
      prompt = systemMessagePromptCreate
        .replace("{instructions}", fcr.instructions)
        .replace("{filename}", fcr.snippet.file);
    }

    const body = {
      prompt: prompt,
      snippets: Object.values(fcr.readOnlySnippets),
    };
    const additionalMessages: Message[] = [];
    var currentIterationContents = (fcr.snippet.entireFile || "").replace(
      /\\n/g,
      "\\n",
    );
    let errorMessage = "";
    let userMessage = formatUserMessage(
      fcr.instructions,
      currentIterationContents,
      Object.values(fcr.readOnlySnippets),
      patches,
      changeType,
    );

    if (changeType === "create") {
      userMessage =
        systemMessagePromptCreate
          .replace("{instructions}", fcr.instructions)
          .replace("{filename}", fcr.snippet.file) + userMessage;
    }

    isRunningRef.current = true;
    setScriptOutput(validationOutput);
    setStreamData("");
    if (!hideMerge) {
      setFileChangeRequests((prev: FileChangeRequest[]) => {
        setHideMerge(true, fcr);
        setFileForFCR(
          prev[index].snippet.entireFile,
          fcr,
          fileChangeRequests,
          setFileChangeRequests,
        );
        return prev;
      });
    }
    const maxIterations = 3;
    for (let i = 0; i <= maxIterations; i++) {
      if (!isRunningRef.current) {
        setIsLoading(false, fcr, fileChangeRequests, setFileChangeRequests);
        return;
      }
      if (i !== 0) {
        var retryMessage = "";
        if (fcr.snippet.entireFile === currentIterationContents) {
          retryMessage = retryChangesMadePrompt.replace(
            "{changes_made}",
            createPatch(
              fcr.snippet.file,
              fcr.snippet.entireFile,
              currentIterationContents,
            ),
          );
        } else {
          retryMessage = retryPrompt;
        }
        retryMessage = retryMessage.replace(
          "{error_message}",
          errorMessage.trim(),
        );
        userMessage = retryMessage;
      }
      setLoadingMessage("Queued...");
      const response = await fetch(url, {
        method: "POST",
        body: JSON.stringify({
          ...body,
          fileContents: currentIterationContents,
          additionalMessages,
          userMessage,
        }),
      });
      setLoadingMessage("Generating code...");
      additionalMessages.push({ role: "user", content: userMessage });
      errorMessage = "";
      var currentContents = currentIterationContents;
      const updateIfChanged = (newContents: string) => {
        if (newContents !== currentIterationContents) {
          setFileForFCR(
            newContents,
            fcr,
            fileChangeRequests,
            setFileChangeRequests,
          );
          currentContents = newContents;
        }
      };
      try {
        const reader = response.body!.getReader();
        const decoder = new TextDecoder("utf-8");
        let rawText = String.raw``;

        setHideMerge(false, fcr);
        var j = 0;
        let globalUpdatedFile = ""; // this is really jank and bad but a quick fix because of the async nature of setters in react
        while (isRunningRef.current) {
          var { done, value } = await reader?.read();
          if (done) {
            let updatedFile = "";
            let patchingErrors = "";
            if (changeType == "modify") {
              let [newUpdatedFile, newPatchingErrors] =
                parseRegexFromOpenAIModify(
                  rawText || "",
                  currentIterationContents,
                );
              updatedFile = newUpdatedFile;
              patchingErrors = newPatchingErrors;
            } else if (changeType == "create") {
              let [newUpdatedFile, newPatchingErrors] =
                parseRegexFromOpenAICreate(
                  rawText || "",
                  currentIterationContents,
                );
              updatedFile = newUpdatedFile;
              patchingErrors = newPatchingErrors;
            }
            if (patchingErrors) {
              errorMessage += patchingErrors;
            } else {
              errorMessage = await checkForErrors(
                fcr.snippet.file,
                fcr.snippet.entireFile,
                updatedFile,
              );
            }
            additionalMessages.push({ role: "assistant", content: rawText });
            updateIfChanged(updatedFile);
            globalUpdatedFile = updatedFile;
            rawText += "\n\n";
            setStreamData((prev) => prev + "\n\n");
            break;
          }
          const text = decoder.decode(value);
          rawText += text;
          setStreamData((prev: string) => prev + text);
          try {
            let updatedFile = "";
            let _ = "";
            if (changeType == "modify") {
              [updatedFile, _] = parseRegexFromOpenAIModify(
                rawText,
                currentIterationContents,
              );
            } else if (changeType == "create") {
              [updatedFile, _] = parseRegexFromOpenAICreate(
                rawText,
                currentIterationContents,
              );
            }
            if (j % 3 == 0) {
              updateIfChanged(updatedFile);
            }
            j += 1;
          } catch (e) {
            console.error(e);
          }
        }
        if (!isRunningRef.current) {
          setIsLoading(false, fcr, fileChangeRequests, setFileChangeRequests);
          setLoadingMessage("");
          setStatusForFCR(
            "idle",
            fcr,
            fileChangeRequests,
            setFileChangeRequests,
          );
          return;
        }
        setHideMerge(false, fcr);
        const changeLineCount = Math.abs(
          fcr.snippet.entireFile.split("\n").length -
            globalUpdatedFile.split("\n").length,
        );
        const changeCharCount = Math.abs(
          fcr.snippet.entireFile.length - globalUpdatedFile.length,
        );
        if (errorMessage.length > 0) {
          console.error("errorMessage in loop", errorMessage);
          toast.error(
            "An error occured while generating your code." +
              (i < 3 ? " Retrying..." : " Retried 4 times so I will give up."),
            {
              description: errorMessage.slice(0, 800),
              action: { label: "Dismiss", onClick: () => {} },
            },
          );
          validationOutput += "\n\n" + errorMessage;
          setScriptOutput(validationOutput);
          setIsLoading(false, fcr, fileChangeRequests, setFileChangeRequests);
          setStatusForFCR(
            "in-progress",
            fcr,
            fileChangeRequests,
            setFileChangeRequests,
          );
          setLoadingMessage("Retrying...");
        } else {
          toast.success(`Successfully modified file!`, {
            description: [
              <div key="stdout">{`There were ${changeLineCount} line and ${changeCharCount} character changes made.`}</div>,
            ],
            action: { label: "Dismiss", onClick: () => {} },
          });
          const newDiff = Diff.createPatch(
            filePath,
            fcr.snippet.entireFile,
            fcr.newContents,
          );
          setIsLoading(false, fcr, fileChangeRequests, setFileChangeRequests);
          setDiffForFCR(
            newDiff,
            fcr,
            fileChangeRequests,
            setFileChangeRequests,
          );
          isRunningRef.current = false;
          break;
        }
      } catch (e: any) {
        console.error("errorMessage in except block", errorMessage);
        toast.error("An error occured while generating your code.", {
          description: e,
          action: { label: "Dismiss", onClick: () => {} },
        });
        if (i === maxIterations) {
          setIsLoading(false, fcr, fileChangeRequests, setFileChangeRequests);
          setStatusForFCR(
            "error",
            fcr,
            fileChangeRequests,
            setFileChangeRequests,
          );
          isRunningRef.current = false;
          setLoadingMessage("");
          return;
        }
      }
    }
    setIsLoading(false, fcr, fileChangeRequests, setFileChangeRequests);
    setStatusForFCR("done", fcr, fileChangeRequests, setFileChangeRequests);
    isRunningRef.current = false;
    setLoadingMessage("");
    return;
  };

  // syncronously modify/create all files
  const getAllFileChanges = async (fcrs: FileChangeRequest[]) => {
    for (let index = 0; index < fcrs.length; index++) {
      const fcr = fcrs[index];
      await getFileChanges(fcr, index);
    }
  };

  const saveAllFiles = async (fcrs: FileChangeRequest[]) => {
    for await (const [index, fcr] of fcrs.entries()) {
      setOldFileForFCR(
        fcr.newContents,
        fcr,
        fileChangeRequests,
        setFileChangeRequests,
      );
      setHideMerge(true, fcr);
      await writeFile(repoName, fcr.snippet.file, fcr.newContents);
    }
    toast.success(`Succesfully saved ${fcrs.length} files!`, {
      action: { label: "Dismiss", onClick: () => {} },
    });
  };

  const syncAllFiles = async () => {
    fileChangeRequests.forEach(
      async (fcr: FileChangeRequest, index: number) => {
        const response = await getFile(repoName, fcr.snippet.file);
        setFileForFCR(
          response.contents,
          fcr,
          fileChangeRequests,
          setFileChangeRequests,
        );
        setOldFileForFCR(
          response.contents,
          fcr,
          fileChangeRequests,
          setFileChangeRequests,
        );
        setIsLoading(false, fcr, fileChangeRequests, setFileChangeRequests);
      },
    );
  };
  return (
    <ResizablePanel defaultSize={35} className="p-6 h-[90vh]">
      <Tabs
        defaultValue="coding"
        className="h-full w-full"
        value={currentTab}
        onValueChange={(value) => setCurrentTab(value as "planning" | "coding")}
      >
        <div className="flex flex-row justify-between">
          <div className="flex flex-row">
            <TabsList>
              <TabsTrigger value="planning">Planning</TabsTrigger>
              <TabsTrigger value="coding">Coding</TabsTrigger>
            </TabsList>
          </div>
          <div>
            <Dialog
              defaultOpen={repoName === ""}
              open={repoNameCollapsibleOpen}
              onOpenChange={(open) => setRepoNameCollapsibleOpen(open)}
            >
              <Button
                variant="secondary"
                className={`${repoName === "" ? "bg-blue-800 hover:bg-blue-900" : ""} h-full`}
                size="sm"
                onClick={() => setRepoNameCollapsibleOpen((open) => !open)}
              >
                <FaCog />
                &nbsp;&nbsp;Repository Settings
                <span className="sr-only">Toggle</span>
              </Button>
              <DialogContent className="CollapsibleContent">
                <div>
                  <Label className="mb-2">Repository Path</Label>
                  <Input
                    id="name"
                    placeholder="/Users/sweep/path/to/repo"
                    value={currentRepoName}
                    className="col-span-4 w-full"
                    onChange={(e) => setCurrentRepoName(e.target.value)}
                    onBlur={refreshFiles}
                  />
                  <p className="text-sm text-muted-foreground mb-4">
                    Absolute path to your repository.
                  </p>
                  <Label className="mb-2">Blocked Keywords</Label>
                  <Input
                    className="mb-4"
                    value={currentBlockedGlobs}
                    onChange={(e) => {
                      setCurrentBlockedGlobs(e.target.value);
                    }}
                    onBlur={() => {
                      setBlockedGlobs(currentBlockedGlobs);
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
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>
        <TabsContent
          value="planning"
          className="rounded-xl border h-full p-4 h-[95%]"
        >
          <DashboardPlanning
            repoName={repoName}
            files={files}
            setLoadingMessage={setLoadingMessage}
            setCurrentTab={setCurrentTab}
          />
        </TabsContent>
        <TabsContent value="coding" className="h-full">
          <div className="flex flex-col h-[95%]">
            <DashboardInstructions
              filePath={filePath}
              repoName={repoName}
              files={files}
              directories={directories}
              currentFileChangeRequestIndex={currentFileChangeRequestIndex}
              setCurrentFileChangeRequestIndex={
                setCurrentFileChangeRequestIndex
              }
              getFileChanges={getFileChanges}
              isRunningRef={isRunningRef}
              syncAllFiles={syncAllFiles}
              getAllFileChanges={() => getAllFileChanges(fileChangeRequests)}
              setCurrentTab={setCurrentTab}
            />
            <Collapsible
              open={validationScriptCollapsibleOpen}
              className="border-2 rounded p-4"
            >
              <div className="flex flex-row justify-between items-center">
                <Label className="mb-0 flex flex-row items-center">
                  Checks&nbsp;
                  <AlertDialog open={alertDialogOpen}>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="rounded-lg ml-1 mr-2"
                      onClick={() => setAlertDialogOpen(true)}
                    >
                      <FaQuestion style={{ fontSize: 12 }} />
                    </Button>
                    <Switch
                      checked={doValidate}
                      onClick={() => setDoValidate(!doValidate)}
                      disabled={fileChangeRequests.some(
                        (fcr: FileChangeRequest) => fcr.isLoading,
                      )}
                    />
                    <AlertDialogContent className="p-12">
                      <AlertDialogHeader>
                        <AlertDialogTitle className="text-5xl mb-2">
                          Test and Validation Scripts
                        </AlertDialogTitle>
                        <AlertDialogDescription className="text-md pt-4">
                          <p>
                            We highly recommend setting up the validation script
                            to allow Sweep to iterate against static analysis
                            tools to ensure valid code is generated. You can
                            this off by clicking the switch.
                          </p>
                          <h2 className="text-2xl mt-4 mb-2 text-zinc-100">
                            Validation Script
                          </h2>
                          <p>
                            Sweep runs validation after every edit, and will try
                            to auto-fix any errors.
                            <br />
                            <br />
                            We recommend a syntax checker (a formatter suffices)
                            and a linter. We also recommend using your local
                            environment, to ensure we use your dependencies.
                            <br />
                            <br />
                            For example, for Python you can use:
                            <pre className="py-4">
                              <code>
                                python -m py_compile $FILE_PATH
                                <br />
                                pylint $FILE_PATH --error-only
                              </code>
                            </pre>
                            And for JavaScript you can use:
                            <pre className="py-4">
                              <code>
                                prettier $FILE_PATH
                                <br />
                                eslint $FILE_PATH
                              </code>
                            </pre>
                          </p>
                          <h2 className="text-2xl mt-4 mb-2 text-zinc-100">
                            Test Script
                          </h2>
                          <p>
                            You can run tests after all the files have been
                            edited by Sweep.
                            <br />
                            <br />
                            E.g. For example, for Python you can use:
                            <pre className="py-4">pytest $FILE_PATH</pre>
                            And for JavaScript you can use:
                            <pre className="py-4">jest $FILE_PATH</pre>
                          </p>
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel
                          onClick={() => setAlertDialogOpen(false)}
                        >
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
                    posthog.capture("run_tests", {
                      name: "Run Tests",
                      repoName: repoName,
                      filePath: filePath,
                      validationScript: validationScript,
                      testScript: testScript,
                    });
                    await runScriptWrapper(file);
                  }}
                  disabled={
                    fileChangeRequests.some(
                      (fcr: FileChangeRequest) => fcr.isLoading,
                    ) || !doValidate
                  }
                  size="sm"
                  className="mr-2"
                >
                  <FaPlay />
                  &nbsp;&nbsp;Run Tests
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    setValidationScriptCollapsibleOpen((open: boolean) => !open)
                  }
                >
                  {!validationScriptCollapsibleOpen ? "Expand" : "Collapse"}
                  &nbsp;&nbsp;
                  <CaretSortIcon className="h-4 w-4" />
                  <span className="sr-only">Toggle</span>
                </Button>
              </div>
              <CollapsibleContent className="pt-2 CollapsibleContent">
                <Label className="mb-0">Validation Script&nbsp;</Label>
                <Textarea
                  id="script-input"
                  placeholder={validationScriptPlaceholder}
                  className="col-span-4 w-full font-mono height-fit-content"
                  value={validationScript}
                  onChange={(e) => setValidationScript(e.target.value)}
                  disabled={
                    fileChangeRequests.some(
                      (fcr: FileChangeRequest) => fcr.isLoading,
                    ) || !doValidate
                  }
                ></Textarea>
                <Label className="mb-0">Test Script</Label>
                <Textarea
                  id="script-input"
                  placeholder={testScriptPlaceholder}
                  className="col-span-4 w-full font-mono height-fit-content"
                  value={testScript}
                  onChange={(e) => setTestScript(e.target.value)}
                  disabled={
                    fileChangeRequests.some(
                      (fcr: FileChangeRequest) => fcr.isLoading,
                    ) || !doValidate
                  }
                ></Textarea>
                <p className="text-sm text-muted-foreground mb-4">
                  Use $FILE_PATH to refer to the file you selected. E.g. `python
                  $FILE_PATH`.
                </p>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </TabsContent>
      </Tabs>
    </ResizablePanel>
  );
};

export default DashboardActions;
