import { CaretSortIcon, CheckIcon } from "@radix-ui/react-icons";
import { Label } from "@radix-ui/react-label";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@radix-ui/react-popover";
import {
  Command,
  CommandInput,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "../ui/command";
import React, { useState } from "react";
import { getFile } from "../../lib/api.service";
import { Snippet } from "../../lib/search";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { Textarea } from "../ui/textarea";
import { FileChangeRequest } from "../../lib/types";
import { ScrollArea } from "../ui/scroll-area";
import { FaPlay } from "react-icons/fa";
import { useLocalStorage } from "usehooks-ts";

const testCasePlaceholder = `Example:
1. Modify the class name to be something more descriptive
2. Add a print statement to the front of each function to describe what each function does.`;

const instructionsPlaceholder = `Example: add a print statement to the front of each function to describe what each function does.`;

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
}: any) => {
  return (
    <Tabs defaultValue="plan" className="grow">
      {/* <TabsList>
                <TabsTrigger value="plan">Plan</TabsTrigger>
                <TabsTrigger value="modify">Modify</TabsTrigger>
            </TabsList> */}
      <TabsContent value="plan">
        <div className="h-96 border rounded-md overflow-auto p-2">
          <Popover open={open} onOpenChange={setOpen} className="mb-4">
            <div className="flex flex-row mb-2">
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
                        setFileChangeRequests((prev) => {
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
                            },
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
              <div key={index} className="mb-4">
                <div className="flex flex-row justify-between p-2 bg-zinc-900 rounded font-sm font-mono items-center">
                  <span>
                    {fileChangeRequest.snippet.file}:
                    {fileChangeRequest.snippet.start}-
                    {fileChangeRequest.snippet.end}
                  </span>
                  <div className="grow"></div>
                  <Button
                    variant="secondary"
                    size="sm"
                    // onClick={() => {

                    // }}
                  >
                    {fileChangeRequest.changeType.toUpperCase()}&nbsp;
                    <FaPlay />
                  </Button>
                </div>
                <Textarea
                  placeholder={instructionsPlaceholder}
                  value={fileChangeRequest.instructions}
                  onChange={(e) => {
                    setFileChangeRequests((prev) => [
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
            <div className="p-2">No files added yet.</div>
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
        <Popover open={open} onOpenChange={setOpen} className="mb-4">
          <div className="flex flex-row mb-2">
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
              <CommandEmpty>No file found.</CommandEmpty>
              <CommandGroup>
                {files.map((file: any) => (
                  <CommandItem
                    key={file.value}
                    value={file.value}
                    onSelect={async (currentValue) => {
                      const contents = (await getFile(repoName, file.value))
                        .contents;
                      setSnippets((prev) => {
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
