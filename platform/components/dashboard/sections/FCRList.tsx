import React, { ReactNode, memo, useState } from "react";
import { Snippet } from "../../../lib/search";
import { FileChangeRequest, snippetKey } from "../../../lib/types";
import { DragDropContext, Droppable, Draggable } from "react-beautiful-dnd";
import FCRCreate from "./FCRCreate";
import FCRModify from "./FCRModify";
import { SuggestionDataItem } from "react-mentions";

const FCRList = memo(function FCRList({
  repoName,
  files,
  fileChangeRequests,
  setFileChangeRequests,
  currentFileChangeRequestIndex,
  setCurrentFileChangeRequestIndex,
  getFileChanges,
  setReadOnlySnippetForFCR,
  removeReadOnlySnippetForFCR,
  removeFileChangeRequest,
  isRunningRef,
  setStatusForFCR
}: {
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
  setStatusForFCR: (newStatus: "queued" | "in-progress" | "done" | "error" | "idle", fcr: FileChangeRequest) => void;
}) {
  const getDynamicClassNames = (fcr: FileChangeRequest, index: number) => {
    let classNames = "";
    if (index === currentFileChangeRequestIndex) {
      // current selected fcr
      classNames += " font-extrabold text-white ";
    } else {
      classNames += " text-zinc-300 ";
    }
    // background highlighting
    if (fcr.status === "in-progress") {
      // is being generated
      classNames += " bg-orange-900 ";
    } else if (fcr.status === "done") {
      // has completed generation
      classNames += " bg-green-900 ";
    } else if (fcr.status === "error") {
      classNames += " bg-red-900 ";
    }
    else if (fcr.status === "idle") {
      // default
      classNames += " bg-zinc-900 ";
    }
    return classNames;
  };

  // helper functions mostly copied from https://codesandbox.io/p/sandbox/k260nyxq9v?file=%2Findex.js%3A36%2C1-40%2C4
  const reorder = (
    fcrList: FileChangeRequest[],
    startIndex: number,
    endIndex: number,
  ) => {
    const result = Array.from(fcrList);
    const [removed] = result.splice(startIndex, 1);
    result.splice(endIndex, 0, removed);

    return result;
  };

  const onDragEnd = (result: any) => {
    if (!result.destination) {
      return;
    }
    const items = reorder(
      fileChangeRequests,
      result.source.index,
      result.destination.index,
    );
    setFileChangeRequests(items);
  };

  const getListStyle = (isDraggingOver: boolean) => ({
    background: isDraggingOver ? "#3c3e3f" : "black",
  });

  const getItemStyle = (isDragging: boolean, draggableStyle: any) => ({
    // some basic styles to make the items look a bit nicer
    userSelect: "none",

    // change background colour if dragging
    background: isDragging ? "black" : "black",

    // styles we need to apply on draggables
    ...draggableStyle,
  });

  const mentionFiles = files.map((file: any) => ({
    id: file.label,
    display: file.label,
  }));

  // this is a work around to the fcr instructions not being updated properly
  // { fcr.file : instructions }
  const [fcrInstructions, setFCRInstructions] = useState(() => {
    let newMap: { [key: string]: string } = {};
    fileChangeRequests.forEach((fcr: FileChangeRequest) => {
      newMap[snippetKey(fcr.snippet)] = fcr.instructions;
    });
    return newMap;
  });

  const setUserSuggestion = (
    suggestion: SuggestionDataItem,
    search: string,
    highlightedDisplay: ReactNode,
    index: number,
    focused: boolean,
  ) => {
    const maxLength = 50;
    const suggestedFileName =
      suggestion.display!.length < maxLength
        ? suggestion.display
        : "..." +
        suggestion.display!.slice(
          suggestion.display!.length - maxLength,
          suggestion.display!.length,
        );
    if (index > 10) {
      return null;
    }
    return (
      <div
        className={`user ${focused ? "bg-zinc-800" : "bg-zinc-900"} p-2 text-sm hover:text-white`}
      >
        {suggestedFileName}
      </div>
    );
  };

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <Droppable droppableId="droppable">
        {(provided: any, snapshot: any) => (
          <div
            {...provided.droppableProps}
            ref={provided.innerRef}
            style={getListStyle(snapshot.isDraggingOver)}
          >
            {fileChangeRequests.map((fcr: FileChangeRequest, index: number) => (
              (fcr.changeType == "create") ? (
                <FCRCreate
                  repoName={repoName}
                  setFileChangeRequests={setFileChangeRequests}
                  setCurrentFileChangeRequestIndex={setCurrentFileChangeRequestIndex}
                  getFileChanges={getFileChanges}
                  setReadOnlySnippetForFCR={setReadOnlySnippetForFCR}
                  removeReadOnlySnippetForFCR={removeReadOnlySnippetForFCR}
                  removeFileChangeRequest={removeFileChangeRequest}
                  isRunningRef={isRunningRef}
                  fcr={fcr}
                  index={index}
                  getDynamicClassNames={getDynamicClassNames}
                  getItemStyle={getItemStyle}
                  mentionFiles={mentionFiles}
                  fcrInstructions={fcrInstructions}
                  setFCRInstructions={setFCRInstructions}
                  setUserSuggestion={setUserSuggestion}
                  key={index}
                  setStatusForFCR={setStatusForFCR}
                />
              ) : (
                <FCRModify
                  key={index}
                  repoName={repoName}
                  setFileChangeRequests={setFileChangeRequests}
                  setCurrentFileChangeRequestIndex={setCurrentFileChangeRequestIndex}
                  getFileChanges={getFileChanges}
                  setReadOnlySnippetForFCR={setReadOnlySnippetForFCR}
                  removeReadOnlySnippetForFCR={removeReadOnlySnippetForFCR}
                  removeFileChangeRequest={removeFileChangeRequest}
                  isRunningRef={isRunningRef}
                  fcr={fcr}
                  index={index}
                  getDynamicClassNames={getDynamicClassNames}
                  getItemStyle={getItemStyle}
                  mentionFiles={mentionFiles}
                  fcrInstructions={fcrInstructions}
                  setFCRInstructions={setFCRInstructions}
                  setUserSuggestion={setUserSuggestion}
                  setStatusForFCR={setStatusForFCR}
                />
              )
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </DragDropContext>
  );
});

export default FCRList;
