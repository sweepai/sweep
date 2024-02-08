"use client";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../ui/resizable";
import { Textarea } from "../ui/textarea";
import React, { useCallback, useEffect, useState } from "react";
import FileSelector from "./FileSelector";
import DashboardActions from "./DashboardActions";
import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { FileChangeRequest, fcrEqual } from "../../lib/types";
import getFiles, { getFile, writeFile } from "../../lib/api.service";
import { usePostHog } from "posthog-js/react";
import { posthogMetadataScript } from "../../lib/posthog";
import { FaArrowsRotate, FaCheck } from "react-icons/fa6";
import { toast } from "sonner";

const blockedPaths = [
  ".git",
  "node_modules",
  "venv",
  "__pycache__",
  ".next",
  "cache",
  "logs",
  "sweep",
  "install_assistant.sh"
];

const versionScript = `timestamp=$(git log -1 --format="%at")
[[ "$OSTYPE" == "linux-gnu"* ]] && date -d @$timestamp +%y.%m.%d.%H || date -r $timestamp +%y.%m.%d.%H
`;

const DashboardDisplay = () => {
  const [streamData, setStreamData] = useState("");
  const [outputToggle, setOutputToggle] = useState("script");
  const [scriptOutput = "" as string, setScriptOutput] = useLocalStorage(
    "scriptOutput",
    "",
  );
  const [repoName, setRepoName] = useLocalStorage("repoName", "");
  const [fileLimit, setFileLimit] = useLocalStorage<number>("fileLimit", 10000);
  const [blockedGlobs, setBlockedGlobs] = useLocalStorage(
    "blockedGlobs",
    blockedPaths.join(", "),
  );
  const [fileChangeRequests = [], setFileChangeRequests] = useState<
    FileChangeRequest[]
  >([]);
  const [currentFileChangeRequestIndex, setCurrentFileChangeRequestIndex] =
    useLocalStorage("currentFileChangeRequestIndex", 0);
  const [versionNumber, setVersionNumber] = useState("");

  const [files = [], setFiles] = useLocalStorage<{ label: string; name: string }[]>("files",[]);
  const [directories = [], setDirectories] = useLocalStorage<{ label: string; name: string }[]>("directories",[]);
  const [loadingMessage = "", setLoadingMessage] = useState("" as string)

  const filePath =
    fileChangeRequests[currentFileChangeRequestIndex]?.snippet.file;
  const oldFile =
    fileChangeRequests[currentFileChangeRequestIndex]?.snippet.entireFile;
  const file = fileChangeRequests[currentFileChangeRequestIndex]?.newContents;
  const hideMerge =
    fileChangeRequests[currentFileChangeRequestIndex]?.hideMerge;

  const posthog = usePostHog();

  const undefinedCheck = (variable: any) => {
    if (typeof variable === "undefined") {
      throw new Error("Variable is undefined");
    }
  };

  const setIsLoading = (newIsLoading: boolean, fcr: FileChangeRequest) => {
    try {
      const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr)
      );
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev) => {
        return [
          ...prev.slice(0, fcrIndex),
          {
            ...prev[fcrIndex],
            isLoading: newIsLoading,
          },
          ...prev.slice(fcrIndex + 1),
        ];
      });
    } catch (error) {
      console.error("Error in setIsLoading: ", error);
    }
  };

  const setStatusForFCR = (newStatus: "queued" | "in-progress" | "done" | "error" | "idle", fcr: FileChangeRequest) => {
    try {
      const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr)
      );
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev) => {
        return [
          ...prev.slice(0, fcrIndex),
          {
            ...prev[fcrIndex],
            status: newStatus,
          },
          ...prev.slice(fcrIndex + 1),
        ];
      });
    } catch (error) {
      console.error("Error in setStatus: ", error);
    }
  };

  const setStatusForAll = (newStatus: "queued" | "in-progress" | "done" | "error" | "idle") => {
    setFileChangeRequests((newFileChangeRequests) => {
      return newFileChangeRequests.map((fileChangeRequest) => {
        return {
          ...fileChangeRequest,
          status: newStatus,
        };
      });
    });
  }

  const setHideMerge = useCallback((newHideMerge: boolean, fcr: FileChangeRequest) => {
    try {
      const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr)
      );
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev) => {
        return [
          ...prev.slice(0, fcrIndex),
          {
            ...prev[fcrIndex],
            hideMerge: newHideMerge,
          },
          ...prev.slice(fcrIndex + 1),
        ];
      });
    } catch (error) {
      console.error("Error in setHideMerge: ", error);
    }
  }, [fileChangeRequests]);

  const setHideMergeAll = (newHideMerge: boolean) => {
    setFileChangeRequests((newFileChangeRequests) => {
      return newFileChangeRequests.map((fileChangeRequest) => {
        return {
          ...fileChangeRequest,
          hideMerge: newHideMerge,
        };
      });
    });
  };

  const setOldFile = useCallback((newOldFile: string) => {
    setCurrentFileChangeRequestIndex((index) => {
      setFileChangeRequests((newFileChangeRequests) => {
        return [
          ...newFileChangeRequests.slice(0, index),
          {
            ...newFileChangeRequests[index],
            snippet: {
              ...newFileChangeRequests[index].snippet,
              entireFile: newOldFile,
            },
          },
          ...newFileChangeRequests.slice(index + 1),
        ];
      });
      return index;
    });
  }, []);

  const setOldFileForFCR = (newOldFile: string, fcr: FileChangeRequest) => {
    try {
      const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr)
      );
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev) => {
        return [
          ...prev.slice(0, fcrIndex),
          {
            ...prev[fcrIndex],
            snippet: {
              ...prev[fcrIndex].snippet,
              entireFile: newOldFile,
            },
          },
          ...prev.slice(fcrIndex + 1),
        ];
      });
    } catch (error) {
      console.error("Error in setOldFileForFCR: ", error);
    }
  };

  const setFile = useCallback((newFile: string) => {
    setCurrentFileChangeRequestIndex((index) => {
      setFileChangeRequests((newFileChangeRequests) => {
        return [
          ...newFileChangeRequests.slice(0, index),
          {
            ...newFileChangeRequests[index],
            newContents: newFile,
          },
          ...newFileChangeRequests.slice(index + 1),
        ];
      });
      return index;
    });
  }, []);

  const setFileForFCR = (newFile: string, fcr: FileChangeRequest) => {
    try {
      const fcrIndex = fileChangeRequests.findIndex(
        (fileChangeRequest: FileChangeRequest) =>
          fcrEqual(fileChangeRequest, fcr)
      );
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev) => {
        return [
          ...prev.slice(0, fcrIndex),
          {
            ...prev[fcrIndex],
            newContents: newFile,
          },
          ...prev.slice(fcrIndex + 1),
        ];
      });
    } catch (error) {
      console.error("Error in setFileForFCR: ", error);
    }
  };

  const removeFileChangeRequest = (fcr: FileChangeRequest) => {
    try {
      const fcrIndex = fileChangeRequests.findIndex(
        (fileChangeRequest: FileChangeRequest) =>
          fcrEqual(fileChangeRequest, fcr)
      );
      undefinedCheck(fcrIndex);
      setFileChangeRequests((prev: FileChangeRequest[]) => {
        return [...prev.slice(0, fcrIndex), ...prev.slice(fcrIndex! + 1)];
      });
    } catch (error) {
      console.error("Error in removeFileChangeRequest: ", error);
    }
  };

  useEffect(() => {
    (async () => {
      const filesAndDirectories = await getFiles(repoName, blockedGlobs, fileLimit);
      let newFiles = filesAndDirectories.sortedFiles;
      let directories = filesAndDirectories.directories;
      newFiles = newFiles.map((file: string) => {
        return { value: file, label: file };
      });
      directories = directories.map((directory: string) => {
        return { value: directory + "/", label: directory + "/" };
      })
      setFiles(newFiles);
      setDirectories(directories)
    })();
  }, [repoName, blockedGlobs, fileLimit]);

  useEffect(() => {
    let textarea = document.getElementById("llm-output") as HTMLTextAreaElement;
    const delta = 50; // Define a delta for the inequality check
    if (Math.abs(textarea.scrollHeight - textarea.scrollTop - textarea.clientHeight) < delta) {
      textarea.scrollTop = textarea.scrollHeight;
    }
  }, [streamData]);

  useEffect(() => {
    (async () => {
      const body = {
        repo: repoName,
        filePath,
        script: versionScript
      };
      const result = await fetch("/api/run?", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const object = await result.json();
      const versionNumberString = object.stdout;
      setVersionNumber("v" + versionNumberString);
    })();
  }, []);

  useEffect(() => {
    (async () => {
      const body = { repo: repoName, filePath, script: posthogMetadataScript };
      const result = await fetch("/api/run?", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const object = await result.json();
      const metadata = JSON.parse(object.stdout);
      posthog?.identify(
        metadata.email === "N/A"
          ? metadata.email
          : `${metadata.whoami}@${metadata.hostname}`,
        metadata,
      );
    })();
  }, [posthog]);

  return (
    <>
      {loadingMessage && (
        <div className="p-2 fixed bottom-12 right-12 text-center z-10 flex flex-col items-center" style={{ borderRadius: '50%', background: 'radial-gradient(circle, rgb(40, 40, 40) 0%, rgba(0, 0, 0, 0) 75%)' }}>
          <img
            className="rounded-full border-zinc-800 border"
            src="https://raw.githubusercontent.com/sweepai/sweep/main/.assets/sweeping.gif"
            alt="Sweeping"
            height={75}
            width={75}
          />
          <p className="mt-2">
            {loadingMessage}
          </p>
        </div>
      )}
      <h1 className="font-bold text-xl">Sweep Assistant</h1>
      <h3 className="text-zinc-400">{versionNumber}</h3>
      <ResizablePanelGroup className="min-h-[80vh] pt-0" direction="horizontal">
        <DashboardActions
          filePath={filePath}
          setScriptOutput={setScriptOutput}
          file={file}
          fileLimit={fileLimit}
          setFileLimit={setFileLimit}
          blockedGlobs={blockedGlobs}
          setBlockedGlobs={setBlockedGlobs}
          hideMerge={hideMerge}
          setHideMerge={setHideMerge}
          repoName={repoName}
          setRepoName={setRepoName}
          setStreamData={setStreamData}
          files={files}
          directories={directories}
          fileChangeRequests={fileChangeRequests}
          setFileChangeRequests={setFileChangeRequests}
          currentFileChangeRequestIndex={currentFileChangeRequestIndex}
          setCurrentFileChangeRequestIndex={setCurrentFileChangeRequestIndex}
          setFileForFCR={setFileForFCR}
          setOldFileForFCR={setOldFileForFCR}
          setIsLoading={setIsLoading}
          undefinedCheck={undefinedCheck}
          removeFileChangeRequest={removeFileChangeRequest}
          setOutputToggle={setOutputToggle}
          setLoadingMessage={setLoadingMessage}
          setStatusForFCR={setStatusForFCR}
          setStatusForAll={setStatusForAll}
        />
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={75}>
          <ResizablePanelGroup direction="vertical">
            <ResizablePanel defaultSize={75} className="flex flex-col mb-4">
              <FileSelector
                filePath={filePath}
                file={file}
                setFile={setFile}
                hideMerge={hideMerge}
                oldFile={oldFile}
                setOldFile={setOldFile}
              ></FileSelector>
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel className="mt-2" defaultSize={25}>
              <div className="flex flex-row items-center">
                <Label className="mr-2">Toggle outputs:</Label>
                <Button
                  className={`mr-2 ${outputToggle === "script" ? "bg-blue-800 hover:bg-blue-900 text-white" : ""}`}
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setOutputToggle("script");
                  }}
                >
                  Validation Output
                </Button>
                <Button
                  className={`${outputToggle === "llm" ? "bg-blue-800 hover:bg-blue-900 text-white" : ""}`}
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setOutputToggle("llm");
                  }}
                >
                  Debug Logs
                </Button>
                <div className="grow"></div>
                <Button
                  className="mr-2"
                  size="sm"
                  variant="secondary"
                  onClick={async () => {
                    const fcr = fileChangeRequests[currentFileChangeRequestIndex]
                    const response = await getFile(
                      repoName,
                      fcr.snippet.file
                    );
                    setFileForFCR(response.contents, fcr);
                    setOldFileForFCR(response.contents, fcr);
                    toast.success("File synced from storage!", {
                      action: { label: "Dismiss", onClick: () => { } },
                    });
                    setCurrentFileChangeRequestIndex(currentFileChangeRequestIndex);
                    setHideMerge(true, fcr);
                    setStatusForFCR("idle", fcr);
                  }}
                  disabled={fileChangeRequests.length === 0 || fileChangeRequests[currentFileChangeRequestIndex]?.isLoading}
                >
                  <FaArrowsRotate />
                </Button>
                <Button
                  size="sm"
                  className="mr-2 bg-green-600 hover:bg-green-700"
                  onClick={async () => {
                    const fcr = fileChangeRequests[currentFileChangeRequestIndex]
                    setOldFileForFCR(fcr.newContents, fcr);
                    setHideMerge(true, fcr);
                    await writeFile(
                      repoName,
                      fcr.snippet.file,
                      fcr.newContents,
                    );
                    toast.success("Succesfully saved file!", {
                      action: { label: "Dismiss", onClick: () => { } },
                    });
                  }}
                  disabled={fileChangeRequests.length === 0 || fileChangeRequests[currentFileChangeRequestIndex]?.isLoading || fileChangeRequests[currentFileChangeRequestIndex]?.hideMerge}
                >
                  <FaCheck />
                </Button>
              </div>
              <Textarea
                className={`mt-4 grow font-mono h-4/5 ${scriptOutput.trim().startsWith("Error") ? "text-red-600" : "text-green-600"}`}
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
                placeholder="ChatGPT's output will be displayed here."
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
