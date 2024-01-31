import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../ui/resizable";
import { Textarea } from "../ui/textarea";
import React, { useEffect, useState } from "react";
import FileSelector from "../shared/FileSelector";
import DashboardActions from "./DashboardActions";
import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { FileChangeRequest } from "../../lib/types";

const blockedPaths = [
  ".git",
  "node_modules",
  "venv",
  "__pycache__",
  ".next",
  "cache",
  "logs",
];

const DashboardDisplay = () => {
  const [branch, setBranch] = useLocalStorage("branch", "");
  const [streamData, setStreamData] = useState("");
  const [outputToggle, setOutputToggle] = useState("script");
  const [scriptOutput, setScriptOutput] = useLocalStorage("scriptOutput", "");
  const [repoName, setRepoName] = useLocalStorage("repoName", "");
  const [fileLimit, setFileLimit] = useLocalStorage<number>("fileLimit", 10000);
  const [blockedGlobs, setBlockedGlobs] = useLocalStorage(
    "blockedGlobs",
    blockedPaths.join(", "),
  );
  const [fileChangeRequests, setFileChangeRequests] = useState<FileChangeRequest[]>([]);
  const [currentFileChangeRequestIndex, setCurrentFileChangeRequestIndex] =
    useLocalStorage("currentFileChangeRequestIndex", 0);

  const [files, setFiles] = useState<{ label: string; name: string }[]>([]);

  const filePath = fileChangeRequests[currentFileChangeRequestIndex]?.snippet.file;
  const oldFile = fileChangeRequests[currentFileChangeRequestIndex]?.snippet.entireFile;
  const file = fileChangeRequests[currentFileChangeRequestIndex]?.newContents;
  const hideMerge = fileChangeRequests[currentFileChangeRequestIndex]?.hideMerge;

  const undefinedCheck = (variable: any) => {
    if (typeof variable === "undefined") {
      throw new Error("Variable is undefined");
    }
  }

  const setIsLoading = (newIsLoading: boolean, index: number) => {
    try {
      undefinedCheck(index);
      setFileChangeRequests(newFileChangeRequests => {
        return [
          ...newFileChangeRequests.slice(0, index),
          {
            ...newFileChangeRequests[index],
            isLoading: newIsLoading
          },
          ...newFileChangeRequests.slice(index + 1)
        ]
      });
    } catch (error) {
      console.error("Error in setIsLoading: ",error);
    }
  }

  const setIsLoadingAll = (newIsLoading: boolean) => {
    setFileChangeRequests(newFileChangeRequests => {
      return newFileChangeRequests.map(fileChangeRequest => {
        return {
          ...fileChangeRequest,
          isLoading: newIsLoading
        }
      })
    })
  }

  const setHideMerge = (newHideMerge: boolean, index: number) => {
    try {
      undefinedCheck(index);
      setFileChangeRequests(newFileChangeRequests => {
        return [
          ...newFileChangeRequests.slice(0, index),
          {
            ...newFileChangeRequests[index],
            hideMerge: newHideMerge
          },
          ...newFileChangeRequests.slice(index + 1)
        ]
      });
    } catch (error) {
      console.error("Error in setHideMerge: ",error);
    }
  }

  const setHideMergeAll = (newHideMerge: boolean) => {
    setFileChangeRequests(newFileChangeRequests => {
      return newFileChangeRequests.map(fileChangeRequest => {
        return {
          ...fileChangeRequest,
          hideMerge: newHideMerge
        }
      })
    })
  }

  const setOldFile = (newOldFile: string) => {
    setCurrentFileChangeRequestIndex(index => {
      setFileChangeRequests(newFileChangeRequests => {
        return [
          ...newFileChangeRequests.slice(0, index),
          {
            ...newFileChangeRequests[index],
            snippet: {
              ...newFileChangeRequests[index].snippet,
              entireFile: newOldFile,
            },
          },
          ...newFileChangeRequests.slice(index + 1)
        ]
      });
      return index;
    })
  }

  const setOldFileByIndex = (newOldFile: string, index: number) => {
    try {
      setFileChangeRequests(newFileChangeRequests => {
        return [
          ...newFileChangeRequests.slice(0, index),
          {
            ...newFileChangeRequests[index],
            snippet: {
              ...newFileChangeRequests[index].snippet,
              entireFile: newOldFile,
            },
          },
          ...newFileChangeRequests.slice(index + 1)
        ]
      });
    } catch (error) {
      console.error("Error in setOldFileByIndex: ",error);
    }
  }

  const setFile = (newFile: string) => {
    setCurrentFileChangeRequestIndex(index => {
      setFileChangeRequests(newFileChangeRequests => {
        return [
          ...newFileChangeRequests.slice(0, index),
          {
            ...newFileChangeRequests[index],
            newContents: newFile
          },
          ...newFileChangeRequests.slice(index + 1)
        ]
      });
      return index;
    });
  }

  const setFileByIndex = (newFile: string, index: number) => {
    try {
      undefinedCheck(index);
      setFileChangeRequests(newFileChangeRequests => {
        return [
          ...newFileChangeRequests.slice(0, index),
          {
            ...newFileChangeRequests[index],
            newContents: newFile
          },
          ...newFileChangeRequests.slice(index + 1)
        ]
      });
    } catch (error) {
      console.error("Error in setFileByIndex: ",error);
    }
  }

  useEffect(() => {
    let textarea = document.getElementById("llm-output") as HTMLTextAreaElement;
    textarea.scrollTop = textarea.scrollHeight;
  }, [streamData]);
  return (
    <>
      <h1 className="font-bold text-xl">Sweep Assistant</h1>
      <ResizablePanelGroup className="min-h-[80vh] pt-0" direction="horizontal">
        <DashboardActions
          filePath={filePath}
          setScriptOutput={setScriptOutput}
          file={file}
          setFile={setFile}
          fileLimit={fileLimit}
          setFileLimit={setFileLimit}
          blockedGlobs={blockedGlobs}
          setBlockedGlobs={setBlockedGlobs}
          hideMerge={hideMerge}
          setHideMerge={setHideMerge}
          branch={branch}
          setBranch={setBranch}
          oldFile={oldFile}
          setOldFile={setOldFile}
          repoName={repoName}
          setRepoName={setRepoName}
          setStreamData={setStreamData}
          files={files}
          fileChangeRequests={fileChangeRequests}
          setFileChangeRequests={setFileChangeRequests}
          currentFileChangeRequestIndex={currentFileChangeRequestIndex}
          setCurrentFileChangeRequestIndex={setCurrentFileChangeRequestIndex}
          setHideMergeAll={setHideMergeAll}
          setFileByIndex={setFileByIndex}
          setOldFileByIndex={setOldFileByIndex}
          setIsLoading={setIsLoading}
          setIsLoadingAll={setIsLoadingAll}
          undefinedCheck={undefinedCheck}
        ></DashboardActions>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={75}>
          <ResizablePanelGroup direction="vertical">
            <ResizablePanel defaultSize={75} className="flex flex-col mb-4">
              <FileSelector
                filePath={filePath}
                file={file}
                setFile={setFile}
                hideMerge={hideMerge}
                setHideMerge={setHideMerge}
                oldFile={oldFile}
                setOldFile={setOldFile}
                repoName={repoName}
                files={files}
                setFiles={setFiles}
                blockedGlobs={blockedGlobs}
                fileLimit={fileLimit}
              ></FileSelector>
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel className="mt-2" defaultSize={25}>
              <Label className="mb-2 mr-2">Toggle outputs:</Label>
              <Button
                className="mr-2"
                variant="secondary"
                onClick={() => {
                  setOutputToggle("script");
                }}
              >
                Validation Output
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setOutputToggle("llm");
                }}
              >
                Debug Logs
              </Button>
              <Textarea
                className={`mt-4 grow font-mono h-4/5 ${scriptOutput.startsWith("Error") ? "text-red-600" : "text-green-600"}`}
                value={scriptOutput}
                id="script-output"
                placeholder="Your script output will be displayed here"
                readOnly
                hidden={outputToggle !== "script"}
              ></Textarea>
              <Textarea
                className={`mt-4 grow font-mono h-4/5`}
                id="llm-output"
                value={streamData}
                placeholder="GPT will display what it is thinking here."
                readOnly
                hidden={outputToggle !== "llm"}
              ></Textarea>
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
      </ResizablePanelGroup>
    </>
  );
};

export default DashboardDisplay;
