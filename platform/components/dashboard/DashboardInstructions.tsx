import React, { memo, forwardRef, Ref } from "react";
import { Snippet } from "../../lib/search";
import { FileChangeRequest } from "../../lib/types";
import ModifyOrCreate from "./sections/ModifyOrCreate";
import FCRList from "./sections/FCRList";
import { Button } from "../ui/button";
import CreationPanel from "./sections/CreationPanel";

const DashboardInstructions = forwardRef(function DashboardInstructions({
  filePath,
  repoName,
  files,
  directories,
  fileChangeRequests,
  setFileChangeRequests,
  currentFileChangeRequestIndex,
  setCurrentFileChangeRequestIndex,
  getFileChanges,
  setReadOnlySnippetForFCR,
  removeReadOnlySnippetForFCR,
  removeFileChangeRequest,
  isRunningRef,
  syncAllFiles,
  getAllFileChanges,
  setStatusForFCR,
  setStatusForAll,
  setCurrentTab,
}: {
  filePath: string;
  repoName: string;
  files: { label: string; name: string }[];
  directories: { label: string; name: string }[];
  fileChangeRequests: FileChangeRequest[];
  setFileChangeRequests: React.Dispatch<
    React.SetStateAction<FileChangeRequest[]>
  >;
  currentFileChangeRequestIndex: number;
  setCurrentFileChangeRequestIndex: React.Dispatch<
    React.SetStateAction<number>
  >;
  getFileChanges: (
    fileChangeRequest: FileChangeRequest,
    index: number,
  ) => Promise<void>;
  setReadOnlySnippetForFCR: (
    fileChangeRequest: FileChangeRequest,
    snippet: Snippet,
  ) => void;
  removeReadOnlySnippetForFCR: (
    fileChangeRequest: FileChangeRequest,
    snippetFile: string,
  ) => void;
  removeFileChangeRequest: (fcr: FileChangeRequest) => void;
  isRunningRef: React.MutableRefObject<boolean>;
  syncAllFiles: () => Promise<void>;
  getAllFileChanges: () => Promise<void>;
  setStatusForFCR: (newStatus: "queued" | "in-progress" | "done" | "error" | "idle", fcr: FileChangeRequest) => void;
  setStatusForAll: (newStatus: "queued" | "in-progress" | "done" | "error" | "idle") => void;
  setCurrentTab: React.Dispatch<React.SetStateAction<"planning" | "coding">>;
}, ref: Ref<HTMLDivElement>) {
  return (
    <div className="grow mb-4 h-full min-h-0 rounded-md p-4 overflow-auto border" ref={ref}>
      <ModifyOrCreate
        filePath={filePath}
        repoName={repoName}
        files={files}
        directories={directories}
        fileChangeRequests={fileChangeRequests}
        setFileChangeRequests={setFileChangeRequests}
        syncAllFiles={syncAllFiles}
        setStatusForAll={setStatusForAll}
      />
      <FCRList
        repoName={repoName}
        files={files}
        fileChangeRequests={fileChangeRequests}
        setFileChangeRequests={setFileChangeRequests}
        currentFileChangeRequestIndex={currentFileChangeRequestIndex}
        setCurrentFileChangeRequestIndex={setCurrentFileChangeRequestIndex}
        getFileChanges={getFileChanges}
        setReadOnlySnippetForFCR={setReadOnlySnippetForFCR}
        removeReadOnlySnippetForFCR={removeReadOnlySnippetForFCR}
        removeFileChangeRequest={removeFileChangeRequest}
        isRunningRef={isRunningRef}
        setStatusForFCR={setStatusForFCR}
      />
      <CreationPanel
        filePath={filePath}
        repoName={repoName}
        files={files}
        directories={directories}
        fileChangeRequests={fileChangeRequests}
        setFileChangeRequests={setFileChangeRequests}
        setCurrentTab={setCurrentTab}
      />
      {fileChangeRequests.length === 0 ? (
        <div className="p-2 text-zinc-300">No File Change Requests added yet.</div>
      ): (
        <div className="text-right mt-2">
          <Button
            variant={"secondary"}
            className="bg-blue-800 hover:bg-blue-900"
            onClick={() => getAllFileChanges()}
          >
            Run all
          </Button>
        </div>
      )}
    </div>
  );
});
export default memo(DashboardInstructions);
