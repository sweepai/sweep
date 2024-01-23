"use client"
import { cn } from "@/lib/utils";
import React, { useCallback, useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from "../ui/command";
import { CaretSortIcon, CheckIcon } from "@radix-ui/react-icons"
import getFiles, { getFile } from "@/lib/api.service";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";
import { javascript } from "@codemirror/lang-javascript";
import CodeMirror, { EditorView } from "@uiw/react-codemirror";
import CodeMirrorMerge from 'react-codemirror-merge';

const extensions = [
    EditorView.theme({
        // '.cm-gutterElement': {
        //     backgroundColor: '#1A1A1C',
        // },
        '.cm-content': {
            backgroundColor: '#0E0E10'
        },
    }),
];


const Original = CodeMirrorMerge.Original;
const Modified = CodeMirrorMerge.Modified;

const FileSelector = (
    { filePath, setFilePath, file, setFile, hideMerge, oldFile, setOldFile, repoName }
    : { filePath: string, setFilePath: any, file: string, setFile: any, hideMerge: boolean, oldFile: string, setOldFile: any, repoName: string } ) => {
    const [open, setOpen] = useState(false)
    const [files, setFiles] = useState([])
    const [value, setValue] = useState("console.log('hello world!');");
    const placeholderText = "Your code will be displayed here once you select a Repository and file."
    const onChange = useCallback((val, viewUpdate) => {
        setValue(val);
        setFile(val)
    }, []);

    useEffect(() => {
        (async () => {
            let newFiles = await getFiles(repoName)
            console.log(newFiles)
            newFiles = newFiles.map((file: any) => {return {value: file, label: file}})
            setFiles(newFiles)
        })()
    }, [repoName])

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
                                    const contents = (await getFile(repoName, file.value)).contents
                                    setFile(contents)
                                    setOldFile(contents)
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
        {hideMerge ? (
            <CodeMirror value={file} extensions={[javascript({ jsx: true }), EditorView.lineWrapping, extensions]} onChange={onChange} theme={vscodeDark} style={{overflow: "auto"}} placeholder={placeholderText}/>
        ): (
            <CodeMirrorMerge theme={vscodeDark} style={{overflow:'auto'}}>
                <Original value={oldFile} extensions={[javascript({ jsx: true }), EditorView.lineWrapping]} onChange={onChange}/>
                <Modified value={file} extensions={[javascript({ jsx: true }), EditorView.lineWrapping]} onChange={onChange}/>
            </CodeMirrorMerge>
        )}
        </>
    )
};

export default FileSelector;
