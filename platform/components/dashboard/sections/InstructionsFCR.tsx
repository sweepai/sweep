import React, { ReactNode, memo, useState } from "react";
import { getFile, writeFile } from "../../../lib/api.service";
import { Snippet } from "../../../lib/search";
import { FileChangeRequest } from "../../../lib/types";
import { FaPlay, FaTimes } from "react-icons/fa";
import { FaArrowsRotate, FaCheck, FaStop, FaTrash } from "react-icons/fa6";
import { toast } from "sonner";
import { Badge } from "../../ui/badge";
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';
import { MentionsInput, Mention, SuggestionDataItem } from 'react-mentions'
import { Button } from "../../ui/button";

const instructionsPlaceholder = `Tell Sweep what modifications you want here. To mention another file Sweep should look at type "@filename"`;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const InstructionsFCR = memo(function InstructionsFCR({
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
  repoName: string;
  files: { label: string; name: string }[];
  fileChangeRequests: FileChangeRequest[];
  setFileChangeRequests: React.Dispatch<React.SetStateAction<FileChangeRequest[]>>;
  currentFileChangeRequestIndex: number;
  setCurrentFileChangeRequestIndex: React.Dispatch<React.SetStateAction<number>>;
  setFileForFCR: (newFile: string, fcr: FileChangeRequest) => void;
  setOldFileForFCR: (newOldFile: string, fcr: FileChangeRequest) => void;
  setHideMerge: (newHideMerge: boolean, fcr: FileChangeRequest) => void;
  getFileChanges: (fileChangeRequest: FileChangeRequest, index: number) => Promise<void>;
  setReadOnlySnippetForFCR: (fileChangeRequest: FileChangeRequest, snippet: Snippet) => void;
  setReadOnlyFilesOpen: (open: boolean, fileChangeRequest: FileChangeRequest) => void;
  removeReadOnlySnippetForFCR: (fileChangeRequest: FileChangeRequest, snippetFile: string) => void;
  removeFileChangeRequest: (fcr: FileChangeRequest) => void;
  isRunningRef: React.MutableRefObject<boolean>
}) {
  const getDynamicClassNames = (fcr: FileChangeRequest, index: number) => {
    let classNames = "";
    if (index === currentFileChangeRequestIndex) { // current selected fcr
      classNames += " font-extrabold text-white ";
    } else {
      classNames += " text-zinc-300 ";
    }
    // background highlighting
    if (fcr.isLoading) { // is being generated
      classNames += " bg-orange-900 ";
    } else if (!fcr.hideMerge && !fcr.isLoading) { // has completed generation
      classNames += " bg-green-900 ";
    }
    else { // default
      classNames += " bg-zinc-900 ";
    }
    return classNames
  }

  // helper functions mostly copied from https://codesandbox.io/p/sandbox/k260nyxq9v?file=%2Findex.js%3A36%2C1-40%2C4
  const reorder = (fcrList: FileChangeRequest[], startIndex: number, endIndex: number) => {
    const result = Array.from(fcrList);
    const [removed] = result.splice(startIndex, 1);
    result.splice(endIndex, 0, removed);

    return result;
  };

  const onDragEnd = (result: any) => {
    if (!result.destination) {
      return;
    }
    const items = reorder(fileChangeRequests, result.source.index, result.destination.index);
    setFileChangeRequests(items);
  }

  const getListStyle = (isDraggingOver: boolean) => ({
    background: isDraggingOver ? "#3c3e3f" : "black",
  })

  const getItemStyle = (isDragging: boolean, draggableStyle: any) => ({
    // some basic styles to make the items look a bit nicer
    userSelect: "none",

    // change background colour if dragging
    background: isDragging ? "black" : "black",

    // styles we need to apply on draggables
    ...draggableStyle
  });

  const mentionFiles = files.map((file: any) => ({ id: file.label, display: file.label }))

  // this is a work around to the fcr instructions not being updated properly
  // { fcr.file : instructions }
  const [fcrInstructions, setFCRInstructions] = useState(() => {
    let newMap: { [key: string]: string } = {};
    fileChangeRequests.forEach((fcr: FileChangeRequest) => {
      newMap[fcr.snippet.file] = fcr.instructions;
    });
    return newMap;
  });

  const setUserSuggestion = (suggestion: SuggestionDataItem, search: string, highlightedDisplay: ReactNode, index: number, focused: boolean) => {
    const maxLength = 50;
    const suggestedFileName = suggestion.display!.length < maxLength ? suggestion.display : "..." + suggestion.display!.slice(suggestion.display!.length - maxLength, suggestion.display!.length);
    return (
      <div className={`user ${focused ? 'bg-zinc-500' : ''} bg-zinc-700 text-white`}>
        {suggestedFileName}
      </div>
    );
  }

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
              <Draggable key={fcr.snippet.file} draggableId={fcr.snippet.file} index={index}>
                {(provided: any, snapshot: any) => (
                  <div
                    ref={provided.innerRef}
                    {...provided.draggableProps}
                    {...provided.dragHandleProps}
                    style={getItemStyle(
                      snapshot.isDragging,
                      provided.draggableProps.style
                    )}
                  >
                    <div key={index} className="mb-4 grow border rounded"
                      onClick={(e) => {
                        setCurrentFileChangeRequestIndex(index)
                      }}
                    >
                      <div className={`justify-between p-2 ${getDynamicClassNames(fcr, index)} rounded font-sm font-mono items-center`}>
                        <div className="flex flex-row w-full items-center">
                          <span>
                            {fcr.snippet.file.split("/")[fcr.snippet.file.split("/").length - 1]}:
                            {fcr.snippet.start}-
                            {fcr.snippet.end}
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
                                  [fcr.snippet.file]: ""
                                }
                              })
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
                          setCurrentFileChangeRequestIndex(index)
                        }}
                        onChange={(e: any) => {
                          console.log("current insturcitons", fcr.instructions)
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
                              [fcr.snippet.file]: e.target.value
                            }
                          })
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
                            console.log("current value", currentValue)
                            console.log("isntructions are", fcr.instructions)
                            const contents = (await getFile(repoName, currentValue.toString()))
                              .contents;
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
                      <div hidden={Object.keys(fcr.readOnlySnippets).length === 0} className="mb-2">
                        {Object.keys(fcr.readOnlySnippets).map((snippetFile: string, index: number) => (
                          <Badge variant="secondary" key={index} className="bg-zinc-800 text-zinc-300">
                            {snippetFile.split("/")[snippetFile.split("/").length - 1]}
                            <FaTimes
                              key={String(index) + "-remove"}
                              className="bg-zinc-800 cursor-pointer"
                              onClick={() => {
                                removeReadOnlySnippetForFCR(fcr, snippetFile);
                              }}
                            />
                          </Badge>
                        ))}
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
                                setCurrentFileChangeRequestIndex(index)
                                getFileChanges(fcr, index)
                              }}
                              disabled={fcr.isLoading}
                            >
                              <FaPlay />&nbsp;{capitalize(fcr.changeType)}
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
                              <FaStop />&nbsp;Cancel
                            </Button>
                          )}
                          <Button
                            className="mr-2"
                            size="sm"
                            variant="secondary"
                            onClick={async () => {
                              const response = await getFile(repoName, fcr.snippet.file);
                              setFileForFCR(response.contents, fcr);
                              setOldFileForFCR(response.contents, fcr);
                              toast.success("File synced from storage!", { action: { label: "Dismiss", onClick: () => { } } });
                              setCurrentFileChangeRequestIndex(index)
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
                              await writeFile(repoName, fcr.snippet.file, fcr.newContents);
                              toast.success("Succesfully saved file!", {
                                action: { label: "Dismiss", onClick: () => { } }
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
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </DragDropContext>)
});
  
export default InstructionsFCR;
