import { CaretSortIcon, CheckIcon } from "@radix-ui/react-icons";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "../ui/popover"
import {
  Command,
  CommandInput,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "../ui/command";
import React from "react";
import { getFile, writeFile } from "../../lib/api.service";
import { Snippet } from "../../lib/search";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Tabs, TabsContent } from "../ui/tabs";
import { Textarea } from "../ui/textarea";
import { FileChangeRequest } from "../../lib/types";
import { FaPlay, FaTimes } from "react-icons/fa";
import { FaArrowsRotate, FaCheck, FaStop, FaTrash } from "react-icons/fa6";
import { toast } from "sonner";
import { Badge } from "../ui/badge";
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';

const testCasePlaceholder = `Example:
1. Modify the class name to be something more descriptive
2. Add a print statement to the front of each function to describe what each function does.`;

const instructionsPlaceholder = `Example: add a docstring after each function definition describing what it does.`;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const DashboardInstructions = ({
  filePath,
  repoName,
  open,
  setOpen,
  files,
  instructions,
  setInstructions,
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
  open: boolean;
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  files: { label: string; name: string }[];
  instructions: string;
  setInstructions: (instructions: string) => void;
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
}) => {
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
    background: isDraggingOver ? "lightgrey" : "black",
  })

  const getItemStyle = (isDragging: boolean, draggableStyle: any) => ({
    // some basic styles to make the items look a bit nicer
    userSelect: "none",
  
    // change background colour if dragging
    background: isDragging ? "black" : "black",
  
    // styles we need to apply on draggables
    ...draggableStyle
  });

  return (
    <Tabs defaultValue="plan" className="grow overflow-auto mb-4 h-full">
      <TabsContent value="plan" className="h-full">
        <div className="grow border rounded-md p-4 overflow-auto h-full">
          <Popover open={open} onOpenChange={setOpen}>
            <div className="flex flex-row mb-4">
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={open}
                  className="w-full justify-between overflow-hidden"
                  disabled={files.length === 0}
                >
                  Add files for Sweep to modify
                  <CaretSortIcon className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
            </div>
            <PopoverContent className="w-full p-0 text-left">
              <Command>
                <CommandInput placeholder="Search file..." className="h-9" />
                <CommandEmpty>No file found.</CommandEmpty>
                <CommandGroup>
                  {files.map((file: any) => (
                    <CommandItem
                      key={file.value}
                      value={file.value}
                      onSelect={async (currentValue) => {
                        // ensure file is not already included
                        if (fileChangeRequests.some((fcr: FileChangeRequest) => fcr.snippet.file === file.value)) {
                          return;
                        }
                        const contents = (await getFile(repoName, file.value))
                          .contents;
                        setFileChangeRequests((prev: FileChangeRequest[]) => {
                          let snippet = {
                            file: file.value,
                            start: 0,
                            end: contents.split("\n").length,
                            entireFile: contents,
                            content: contents, // this is the slice based on start and end, remeber to change this
                          } as Snippet;
                          return [
                            ...prev,
                            {
                              snippet,
                              changeType: "modify",
                              newContents: contents,
                              hideMerge: true,
                              instructions: "",
                              isLoading: false,
                              openReadOnlyFiles: false,
                              readOnlySnippets: {},
                            } as FileChangeRequest,
                          ];
                        });
                        setOpen(false);
                      }}
                    >
                      {file.label}
                      <CheckIcon
                        className={cn(
                          "ml-auto h-4 w-4",
                          filePath === file.value ? "opacity-100" : "opacity-0",
                        )}
                      />
                    </CommandItem>
                  ))}
                </CommandGroup>
              </Command>
            </PopoverContent>
          </Popover>
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
                      }}
                      disabled={fcr.isLoading}
                    >
                      <FaTrash />
                    </Button>
                  </div>
                </div>
                <Textarea
                  className="mb-0"
                  placeholder={instructionsPlaceholder}
                  value={fcr.instructions}
                  onClick={(e) => {
                    setCurrentFileChangeRequestIndex(index)
                  }}
                  onChange={(e) => {
                    setFileChangeRequests((prev: FileChangeRequest[]) => [
                      ...prev.slice(0, index),
                      {
                        ...prev[index],
                        instructions: e.target.value,
                      },
                      ...prev.slice(index + 1),
                    ]);
                  }}
                />
                <Popover open={fcr.openReadOnlyFiles}>
                  <div className="flex flex-row mb-2 p-0">
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={fcr.openReadOnlyFiles}
                        className="w-full justify-between overflow-hidden mt-0 bg-zinc-900 text-zinc-300"
                        disabled={!files || fcr.isLoading}
                        onClick={(e) => {
                          setReadOnlyFilesOpen(!fcr.openReadOnlyFiles, fcr)
                        }}
                      >
                        Add relevant read-only files
                        <CaretSortIcon className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </Button>
                    </PopoverTrigger>
                  </div>
                  <PopoverContent className="w-full p-0 text-left">
                    <Command>
                      <CommandInput placeholder="Search file..." className="h-9" />
                      <CommandEmpty>
                        <div className="text-zinc-300">
                          No file found.
                        </div>
                      </CommandEmpty>
                      <CommandGroup>
                        {files.map((file: any) => (
                          <CommandItem
                            key={file.value}
                            value={file.value}
                            className="mb-0"
                            onSelect={async (currentValue) => {
                              const contents = (await getFile(repoName, file.value))
                                .contents;
                              const newSnippet = {
                                file: file.value,
                                start: 0,
                                end: contents.split("\n").length,
                                entireFile: contents,
                                content: contents, // this is the slice based on start and end, remeber to change this
                              } as Snippet;
                              setReadOnlySnippetForFCR(fcr, newSnippet);
                              setReadOnlyFilesOpen(false, fcr);
                            }}
                          >
                            {file.label}
                            <CheckIcon
                              className={cn(
                                "ml-auto h-4 w-4",
                                filePath === file.value ? "opacity-100" : "opacity-0",
                              )}
                            />
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </Command>
                  </PopoverContent>
                </Popover>
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
                        onClick={(e) => {
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
                        onClick={(e) => {
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
          </DragDropContext>
          {fileChangeRequests.length === 0 && (
            <div className="p-2 text-zinc-300">No files added yet.</div>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
};
export default DashboardInstructions;
