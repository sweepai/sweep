import React, { memo, forwardRef, Ref } from "react";
import { Snippet } from "../../lib/search";
import { FileChangeRequest } from "../../lib/types";
import ModifyOrCreate from "./sections/ModifyOrCreate";
import FCRList from "./sections/FCRList";
import { Button } from "../ui/button";

const DashboardInstructions = forwardRef(function DashboardInstructions({
  filePath,
  repoName,
  files,
  directories,
  fileChangeRequests,
  setFileChangeRequests,
  currentFileChangeRequestIndex,
  setCurrentFileChangeRequestIndex,
  setFileForFCR,
  setOldFileForFCR,
  setHideMerge,
  getFileChanges,
  setReadOnlySnippetForFCR,
  setReadOnlyFilesOpen,
  removeReadOnlySnippetForFCR,
  removeFileChangeRequest,
  isRunningRef,
  syncAllFiles,
  getAllFileChanges,
  setStatusForFCR,
  setStatusForAll
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
  setFileForFCR: (newFile: string, fcr: FileChangeRequest) => void;
  setOldFileForFCR: (newOldFile: string, fcr: FileChangeRequest) => void;
  setHideMerge: (newHideMerge: boolean, fcr: FileChangeRequest) => void;
  getFileChanges: (
    fileChangeRequest: FileChangeRequest,
    index: number,
  ) => Promise<void>;
  setReadOnlySnippetForFCR: (
    fileChangeRequest: FileChangeRequest,
    snippet: Snippet,
  ) => void;
  setReadOnlyFilesOpen: (
    open: boolean,
    fileChangeRequest: FileChangeRequest,
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
        setFileForFCR={setFileForFCR}
        setOldFileForFCR={setOldFileForFCR}
        setHideMerge={setHideMerge}
        getFileChanges={getFileChanges}
        setReadOnlySnippetForFCR={setReadOnlySnippetForFCR}
        setReadOnlyFilesOpen={setReadOnlyFilesOpen}
        removeReadOnlySnippetForFCR={removeReadOnlySnippetForFCR}
        removeFileChangeRequest={removeFileChangeRequest}
        isRunningRef={isRunningRef}
        setStatusForFCR={setStatusForFCR}
      />
      {fileChangeRequests.length === 0 ? (
        <div className="p-2 text-zinc-300">No files added yet. Please click &quot;Modify a file&quot; or &quot;Create a file&quot; to add a file.</div>
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
