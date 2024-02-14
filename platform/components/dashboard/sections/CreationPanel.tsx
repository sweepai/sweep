import { CheckIcon } from "@radix-ui/react-icons";
import { Popover, PopoverTrigger, PopoverContent } from "../../ui/popover";
import {
  Command,
  CommandInput,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "../../ui/command";
import React, { useState } from "react";
import { getFile } from "../../../lib/api.service";
import { Snippet } from "../../../lib/search";
import { cn } from "../../../lib/utils";
import { Button } from "../../ui/button";
import { FileChangeRequest } from "../../../lib/types";
import { FaPlus } from "react-icons/fa6";
import { FileChangeRequestsState } from "../../../state/fcrAtoms";
import { useRecoilState } from "recoil";

const CreationPanel = ({
  filePath,
  repoName,
  files,
  directories,
  setCurrentTab,
}: {
  filePath: string;
  repoName: string;
  files: { label: string; name: string }[];
  directories: { label: string; name: string }[];
  setCurrentTab: React.Dispatch<React.SetStateAction<"planning" | "coding">>;
}) => {
  const [hidePanel, setHidePanel] = useState(true);
  const [openModify, setOpenModify] = useState(false);
  const [openCreate, setOpenCreate] = useState(false);
  const [fileChangeRequests, setFileChangeRequests] = useRecoilState(
    FileChangeRequestsState,
  );

  return (
    <div
      id="creation-panel-wrapper"
      onMouseEnter={() => setHidePanel(false)}
      onMouseLeave={() => setHidePanel(true)}
    >
      <div id="creation-panel-plus-sign-wraper" hidden={!hidePanel}>
        <div className="flex flex-row w-full h-[80px] overflow-auto items-center mb-4">
          <Button
            variant="outline"
            className="w-full h-full justify-center overflow-hidden bg-zinc-800 hover:bg-zinc-900 items-center"
          >
            <FaPlus className="mr-2" />
          </Button>
        </div>
      </div>
      <div id="creation-panel-actions-panel-wrapper" hidden={hidePanel}>
        <div
          id="creation-panel-actions-panel"
          className="flex flex-row w-full h-[80px] mb-4 border rounded items-center"
        >
          <Popover open={openModify} onOpenChange={setOpenModify}>
            <div className="w-full h-full overflow-auto">
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={openModify}
                  className="border rounded-none w-full h-full bg-zinc-800 hover:bg-zinc-900 text-lg"
                >
                  Modify file
                </Button>
              </PopoverTrigger>
            </div>
            <PopoverContent className="w-full p-0 text-left">
              <Command>
                <CommandInput
                  placeholder="Search for a file to modify..."
                  className="h-9"
                />
                <CommandEmpty>No file found.</CommandEmpty>
                <CommandGroup>
                  {files.map((file: any) => (
                    <CommandItem
                      key={file.value}
                      value={file.value}
                      onSelect={async (currentValue) => {
                        // ensure file is not already included
                        if (
                          fileChangeRequests.some(
                            (fcr: FileChangeRequest) =>
                              fcr.snippet.file === file.value,
                          )
                        ) {
                          return;
                        }
                        const contents =
                          (await getFile(repoName, file.value)).contents || "";
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
                              readOnlySnippets: {},
                              diff: "",
                              status: "idle",
                            } as FileChangeRequest,
                          ];
                        });
                        setOpenModify(false);
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
          <Popover open={openCreate} onOpenChange={setOpenCreate}>
            <div className="w-full h-full overflow-auto">
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={openCreate}
                  className="border-2 border-black-900 rounded-none w-full h-full bg-zinc-800 hover:bg-zinc-900 text-lg"
                >
                  Create file
                </Button>
              </PopoverTrigger>
            </div>
            <PopoverContent className="w-full p-0 text-left">
              <Command>
                <CommandInput
                  placeholder="Search for a directory..."
                  className="h-9"
                />
                <CommandEmpty>No directory found.</CommandEmpty>
                <CommandGroup>
                  {directories.map((dir: any) => (
                    <CommandItem
                      key={dir.value}
                      value={dir.value}
                      onSelect={async (currentValue) => {
                        setFileChangeRequests((prev: FileChangeRequest[]) => {
                          let snippet = {
                            file: dir.value,
                            start: 0,
                            end: 0,
                            entireFile: "",
                            content: "",
                          } as Snippet;
                          return [
                            ...prev,
                            {
                              snippet,
                              changeType: "create",
                              newContents: "",
                              hideMerge: true,
                              instructions: "",
                              isLoading: false,
                              readOnlySnippets: {},
                              diff: "",
                              status: "idle",
                            } as FileChangeRequest,
                          ];
                        });
                        setOpenCreate(false);
                      }}
                    >
                      {dir.label}
                      <CheckIcon
                        className={cn(
                          "ml-auto h-4 w-4",
                          filePath === dir.value ? "opacity-100" : "opacity-0",
                        )}
                      />
                    </CommandItem>
                  ))}
                </CommandGroup>
              </Command>
            </PopoverContent>
          </Popover>
          <div className="w-full h-full overflow-auto">
            <Button
              variant="outline"
              role="combobox"
              className="border rounded-none w-full h-full bg-zinc-800 hover:bg-zinc-900 text-lg"
              onClick={() => {
                setCurrentTab("planning");
              }}
            >
              Create plan
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
export default CreationPanel;
