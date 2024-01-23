"use client"
import { cn } from "@/lib/utils";
import React, { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from "../ui/command";
import { CaretSortIcon, CheckIcon } from "@radix-ui/react-icons"
import getFiles, { getFile } from "@/lib/api.service";
import { Textarea } from "../ui/textarea";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";
import { javascript } from "@codemirror/lang-javascript";
import CodeMirror, { EditorView } from "@uiw/react-codemirror";

const FileSelector = ( { filePath, setFilePath, file, setFile } : { filePath: string, setFilePath: any, file: string, setFile: any } ) => {
    const [open, setOpen] = useState(false)
    const [files, setFiles] = useState([])
    
    const [value, setValue] = React.useState("console.log('hello world!');");
    const onChange = React.useCallback((val, viewUpdate) => {
        console.log('val:', val);
        setValue(val);
    }, []);

    useEffect(() => {
        (async () => {
            let newFiles = await getFiles()
            newFiles = newFiles.map((file: any) => {return {value: file, label: file}})
            setFiles(newFiles)
        })()
    }, [])
    return (
        <>
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    className="w-full justify-between">
                    {filePath ? files.find((file: any) => file.value === filePath)?.label : "Select file..."}
                    <CaretSortIcon className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
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
                                    setFilePath(currentValue === filePath ? "" : currentValue)
                                    setOpen(false)
                                    setFile((await getFile(file.value)).contents)
                                }}
                            >
                            {file.label}
                                <CheckIcon
                                    className={cn(
                                        "ml-auto h-4 w-4",
                                        filePath === file.value ? "opacity-100" : "opacity-0"
                                    )}
                                />
                            </CommandItem>
                        ))}
                    </CommandGroup>
                </Command>
            </PopoverContent>
        </Popover>
        <CodeMirror value={file} extensions={[javascript({ jsx: true }), EditorView.lineWrapping]} onChange={onChange} theme={vscodeDark} height="380px"/>
        </>
    )
};

export default FileSelector;