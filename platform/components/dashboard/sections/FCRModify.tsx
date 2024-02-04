import React, { ReactNode, memo, useState } from "react";
import { getFile, writeFile } from "../../../lib/api.service";
import { Snippet } from "../../../lib/search";
import { FileChangeRequest } from "../../../lib/types";
import { FaPlay, FaTimes } from "react-icons/fa";
import { FaArrowsRotate, FaCheck, FaStop, FaTrash } from "react-icons/fa6";
import { toast } from "sonner";
import { Badge } from "../../ui/badge";
import { DragDropContext, Droppable, Draggable } from "react-beautiful-dnd";
import { MentionsInput, Mention, SuggestionDataItem } from "react-mentions";
import { Button } from "../../ui/button";

const instructionsPlaceholder = `Instructions for what to modify. Type "@filename" for Sweep to read another file.`;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
};

const FCRModify = memo(function FCRModify({
  repoName,
  setFileChangeRequests,
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
  fcr,
  index,
  getDynamicClassNames,
  getItemStyle,
  mentionFiles,
  fcrInstructions,
  setFCRInstructions,
  setUserSuggestion,
}: {
  repoName: string;
  setFileChangeRequests: React.Dispatch<
    React.SetStateAction<FileChangeRequest[]>
  >;
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
  fcr: FileChangeRequest;
  index: number;
  getDynamicClassNames: (fcr: FileChangeRequest, index: number) => string;
  getItemStyle: (isDragging: boolean, draggableStyle: any) => any;
  mentionFiles: {id: any;display: any;}[];
  fcrInstructions: { [key: string]: string; };
  setFCRInstructions: React.Dispatch<React.SetStateAction<{ [key: string]: string; }>>;
  setUserSuggestion: (suggestion: SuggestionDataItem, search: string, highlightedDisplay: ReactNode, index: number, focused: boolean) => JSX.Element;
}) {
  return (
    <Draggable
      key={fcr.snippet.file}
      draggableId={fcr.snippet.file}
      index={index}
    >
      {(provided: any, snapshot: any) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          style={getItemStyle(
            snapshot.isDragging,
            provided.draggableProps.style,
          )}
        >
          <div
            key={index}
            className="mb-4 grow border rounded"
            onClick={(e) => {
              setCurrentFileChangeRequestIndex(index);
            }}
          >
            <div
              className={`justify-between p-2 ${getDynamicClassNames(fcr, index)} rounded font-sm font-mono items-center`}
            >
              <div className="flex flex-row w-full items-center">
                <span>
                  {
                    fcr.snippet.file.split("/")[
                    fcr.snippet.file.split("/").length - 1
                    ]
                  }
                  :{fcr.snippet.start}-{fcr.snippet.end}
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  className="mr-2 ml-auto"
                  onClick={async () => {
                    removeFileChangeRequest(fcr);
                    setFCRInstructions((prev: any) => {
                      return {
                        ...prev,
                        [fcr.snippet.file]: "",
                      };
                    });
                  }}
                  disabled={fcr.isLoading}
                >
                  <FaTrash />
                </Button>
              </div>
            </div>
            <MentionsInput
              className="min-h-[50px] w-full rounded-md border border-input bg-background MentionsInput"
              placeholder={instructionsPlaceholder}
              value={fcrInstructions[fcr.snippet.file as string]}
              onClick={(e: any) => {
                setCurrentFileChangeRequestIndex(index);
              }}
              onChange={(e: any) => {
                setFileChangeRequests((prev: FileChangeRequest[]) => [
                  ...prev.slice(0, index),
                  {
                    ...prev[index],
                    instructions: e.target.value,
                  },
                  ...prev.slice(index + 1),
                ]);
                setFCRInstructions((prev: any) => {
                  return {
                    ...prev,
                    [fcr.snippet.file]: e.target.value,
                  };
                });
              }}
              onBlur={(e: any) => {
                // this apparently removes the styling on the mentions, this may be a hack
                setFileChangeRequests((prev: FileChangeRequest[]) => [
                  ...prev.slice(0, index),
                  {
                    ...prev[index],
                    instructions: e.target.value,
                  },
                  ...prev.slice(index + 1),
                ]);
              }}
            >
              <Mention
                trigger="@"
                data={mentionFiles}
                renderSuggestion={setUserSuggestion}
                onAdd={async (currentValue) => {
                  const contents = (
                    await getFile(repoName, currentValue.toString())
                  ).contents;
                  const newSnippet = {
                    file: currentValue,
                    start: 0,
                    end: contents.split("\n").length,
                    entireFile: contents,
                    content: contents, // this is the slice based on start and end, remeber to change this
                  } as Snippet;
                  setReadOnlySnippetForFCR(fcr, newSnippet);
                  setReadOnlyFilesOpen(false, fcr);
                }}
                appendSpaceOnAdd={true}
              />
            </MentionsInput>
            <div
              hidden={Object.keys(fcr.readOnlySnippets).length === 0}
              className="mb-2"
            >
              {Object.keys(fcr.readOnlySnippets).map(
                (snippetFile: string, index: number) => (
                  <Badge
                    variant="secondary"
                    key={index}
                    className="bg-zinc-800 text-zinc-300"
                  >
                    {
                      snippetFile.split("/")[
                      snippetFile.split("/").length - 1
                      ]
                    }
                    <FaTimes
                      key={String(index) + "-remove"}
                      className="bg-zinc-800 cursor-pointer"
                      onClick={() => {
                        removeReadOnlySnippetForFCR(fcr, snippetFile);
                      }}
                    />
                  </Badge>
                ),
              )}
            </div>
            <div className="flex flex-row justify-end w-full pb-2">
              <span>
                {!isRunningRef.current ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mr-2"
                    onClick={(e: any) => {
                      // syncFCRInstructions();
                      //console.log("current fcr", fcr)
                      setCurrentFileChangeRequestIndex(index);
                      getFileChanges(fcr, index);
                    }}
                    disabled={fcr.isLoading}
                  >
                    <FaPlay />
                    &nbsp;{capitalize(fcr.changeType)}
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mr-2"
                    onClick={(e: any) => {
                      isRunningRef.current = false;
                    }}
                  >
                    <FaStop />
                    &nbsp;Cancel
                  </Button>
                )}
                <Button
                  className="mr-2"
                  size="sm"
                  variant="secondary"
                  onClick={async () => {
                    const response = await getFile(
                      repoName,
                      fcr.snippet.file,
                    );
                    setFileForFCR(response.contents, fcr);
                    setOldFileForFCR(response.contents, fcr);
                    toast.success("File synced from storage!", {
                      action: { label: "Dismiss", onClick: () => { } },
                    });
                    setCurrentFileChangeRequestIndex(index);
                    setHideMerge(true, fcr);
                  }}
                  disabled={fcr.isLoading}
                >
                  <FaArrowsRotate />
                </Button>
                <Button
                  size="sm"
                  className="mr-2 bg-green-600 hover:bg-green-700"
                  onClick={async () => {
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
                  disabled={fcr.isLoading || fcr.hideMerge}
                >
                  <FaCheck />
                </Button>
              </span>
            </div>
          </div>
        </div>
      )}
    </Draggable>
  );
});

export default FCRModify;
