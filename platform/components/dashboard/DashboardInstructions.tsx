import { CaretSortIcon, CheckIcon } from "@radix-ui/react-icons";
import { Popover, PopoverTrigger, PopoverContent } from "../ui/popover";
import {
  Command,
  CommandInput,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "../ui/command";
import React, { ReactNode, memo, useCallback, useState } from "react";
import { getFile, writeFile } from "../../lib/api.service";
import { Snippet } from "../../lib/search";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Tabs, TabsContent } from "../ui/tabs";
import { FileChangeRequest } from "../../lib/types";
import { FaPlay, FaTimes } from "react-icons/fa";
import { FaArrowsRotate, FaCheck, FaStop, FaTrash } from "react-icons/fa6";
import { toast } from "sonner";
import { Badge } from "../ui/badge";
import { DragDropContext, Droppable, Draggable } from "react-beautiful-dnd";
import { MentionsInput, Mention, SuggestionDataItem } from "react-mentions";
import InstructionsFCR from "./sections/InstructionsFCR";
import ModifyOrCreate from "./sections/ModifyOrCreate";

const instructionsPlaceholder = `Tell Sweep what modifications you want here. To mention another file Sweep should look at type "@filename"`;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
};

const DashboardInstructions = memo(function DashboardInstructions({
  filePath,
  repoName,
  files,
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
}: {
  filePath: string;
  repoName: string;
  files: { label: string; name: string }[];
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
}) {
  return (
    <Tabs defaultValue="plan" className="grow overflow-auto mb-4 h-full">
      <TabsContent value="plan" className="h-full">
        <div className="grow border rounded-md p-4 overflow-auto h-full">
          <ModifyOrCreate
            filePath={filePath}
            repoName={repoName}
            files={files}
            fileChangeRequests={fileChangeRequests}
            setFileChangeRequests={setFileChangeRequests}
          />
          <InstructionsFCR
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
            <div className="p-2 text-zinc-300">No files added yet.</div>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
});
export default DashboardInstructions;
