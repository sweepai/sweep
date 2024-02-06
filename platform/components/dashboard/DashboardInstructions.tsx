import React, { memo } from "react";
import { Snippet } from "../../lib/search";
import { Tabs, TabsContent } from "../ui/tabs";
import { FileChangeRequest } from "../../lib/types";
import ModifyOrCreate from "./sections/ModifyOrCreate";
import FCRList from "./sections/FCRList";

const DashboardInstructions = function DashboardInstructions({
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
  refreshFiles,
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
  refreshFiles: () => Promise<void>;
}) {
  return (
    <Tabs defaultValue="plan" className="grow mb-4 h-full min-h-0">
      <TabsContent value="plan" className="h-full grow border rounded-md p-4 overflow-auto h-full">
        <ModifyOrCreate
          filePath={filePath}
          repoName={repoName}
          files={files}
          directories={directories}
          fileChangeRequests={fileChangeRequests}
          setFileChangeRequests={setFileChangeRequests}
          refreshFiles={refreshFiles}
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
        />
        {fileChangeRequests.length === 0 && (
          <div className="p-2 text-zinc-300">No files added yet. Please click &quot;Modify a file&quot; or &quot;Create a file&quot; to add a file.</div>
        )}
      </TabsContent>
    </Tabs>
  );
};
export default DashboardInstructions;
