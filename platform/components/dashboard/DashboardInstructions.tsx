import { CaretSortIcon, CheckIcon } from "@radix-ui/react-icons";
import { Label } from "@radix-ui/react-label";
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
import React, { useState } from "react";
import { getFile, writeFile } from "../../lib/api.service";
import { Snippet } from "../../lib/search";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Tabs, TabsContent } from "../ui/tabs";
import { Textarea } from "../ui/textarea";
import { FileChangeRequest } from "../../lib/types";
import { FaPlay } from "react-icons/fa";
import { FaArrowsRotate, FaCheck } from "react-icons/fa6";
import { toast } from "sonner";

const testCasePlaceholder = `Example:
1. Modify the class name to be something more descriptive
2. Add a print statement to the front of each function to describe what each function does.`;

const instructionsPlaceholder = `Example: add a print statement to the front of each function to describe what each function does.`;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const DashboardInstructions = ({
  filePath,
  repoName,
  setSnippets,
  open,
  setOpen,
  files,
  instructions,
  setInstructions,
  fileChangeRequests,
  setFileChangeRequests,
  currentFileChangeRequestIndex,
  setCurrentFileChangeRequestIndex,
  setFileByIndex,
  setOldFileByIndex,
  setHideMerge,
  getFileChanges
}: any) => {
  const [isLoading, setIsLoading] = useState(false);
  return (
    <Tabs defaultValue="plan" className="grow">
      <TabsContent value="plan">
        <div className="h-96 border rounded-md overflow-auto p-4">
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
          {fileChangeRequests.map(
            (fileChangeRequest: FileChangeRequest, index: number) => (
              <div key={index} className="mb-4"
                onClick={(e) => {
                  setCurrentFileChangeRequestIndex(index)
                }}
              >
                <div className={`flex flex-row justify-between p-2 ${index === currentFileChangeRequestIndex ? "bg-blue-900" : fileChangeRequest.hideMerge ? "bg-zinc-900" : "bg-green-900"} rounded font-sm font-mono items-center`}>
                  <span>
                    {fileChangeRequest.snippet.file.split("/")[fileChangeRequest.snippet.file.split("/").length - 1]}:
                    {fileChangeRequest.snippet.start}-
                    {fileChangeRequest.snippet.end}
                  </span>
                  <div className="grow"></div>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mr-2 flex-row flex"
                    onClick={(e) => {
                      setCurrentFileChangeRequestIndex(index)
                      getFileChanges(fileChangeRequest, index)
                      e.preventDefault()
                      e.stopPropagation()
                    }}
                    disabled={isLoading}
                  >
                    <FaPlay />&nbsp;{capitalize(fileChangeRequest.changeType)}
                  </Button>
                  <Button
                    className="mr-2 flex-row flex"
                    size="sm"
                    variant="secondary"
                    onClick={async () => {
                      setIsLoading(true);
                      const response = await getFile(repoName, fileChangeRequest.snippet.file);
                      setFileByIndex(response.contents, index);
                      setOldFileByIndex(response.contents, index);
                      toast.success("File synced from storage!");
                      setIsLoading(false);
                      setCurrentFileChangeRequestIndex(index)
                      setHideMerge(true, index);
                    }}
                    disabled={isLoading}
                  >
                    <FaArrowsRotate />
                  </Button>
                  <Button
                    size="sm"
                    className="mr-2 bg-green-600 hover:bg-green-700"
                    onClick={async () => {
                      setOldFileByIndex(fileChangeRequest.newContents, index);
                      setHideMerge(true, index);
                      await writeFile(repoName, fileChangeRequest.snippet.file, fileChangeRequest.newContents);
                      toast.success("Succesfully saved file!");
                    }}
                    disabled={isLoading || fileChangeRequest.hideMerge}
                  >
                    <FaCheck />
                  </Button>
                </div>
                <Textarea
                  placeholder={instructionsPlaceholder}
                  value={fileChangeRequest.instructions}
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
              </div>
            ),
          )}
          {fileChangeRequests.length === 0 && (
            <div className="p-2 text-zinc-300">No files added yet.</div>
          )}
        </div>
      </TabsContent>
      <TabsContent className="flex flex-col h-full pt-4" value="modify">
        <div className="grow">
          <Label className="mb-2 font-bold">Instructions</Label>
          <Textarea
            id="instructions-input"
            placeholder={testCasePlaceholder}
            value={instructions}
            className="grow mb-4"
            onChange={(e) => setInstructions(e.target.value)}
            style={{ height: "-webkit-fill-available" }}
          ></Textarea>
        </div>
        <Popover open={open} onOpenChange={setOpen}>
          <div className="flex flex-row mb-4 p-2">
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                role="combobox"
                aria-expanded={open}
                className="w-full justify-between overflow-hidden mt-4"
                disabled={!files}
              >
                Add relevant read-only files for Sweep to read
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
                    onSelect={async (currentValue) => {
                      const contents = (await getFile(repoName, file.value))
                        .contents;
                      setSnippets((prev: { [key: string]: Snippet }) => {
                        let newSnippet = {
                          file: file.value,
                          start: 0,
                          end: contents.split("\n").length,
                          entireFile: contents,
                          content: contents, // this is the slice based on start and end, remeber to change this
                        } as Snippet;
                        prev[newSnippet.file] = newSnippet;
                        return prev;
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
      </TabsContent>
    </Tabs>
  );
};
export default DashboardInstructions;
