"use client"
import { cn } from "../../lib/utils";
import React, { useCallback, useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from "../ui/command";
import { CaretSortIcon, CheckIcon } from "@radix-ui/react-icons"
import getFiles, { getFile, writeFile } from "../../lib/api.service";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";
import { FaSave } from "react-icons/fa";

import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { python } from "@codemirror/lang-python";
import { html } from "@codemirror/lang-html";

import CodeMirror, { EditorView } from "@uiw/react-codemirror";
import CodeMirrorMerge from 'react-codemirror-merge';
import { toast } from "sonner";

const getLanguage = (ext: string) => {
    const languageMap: {[key: string]: any } = {
        js: javascript(),
        jsx: javascript({ jsx: true }),
        ts: javascript({ typescript: true }),
        tsx: javascript({ typescript: true, jsx: true }),
        html: html(),
        ejs: html(),
        erb: html(),
        py: python(),
        kt: java(),
    }
    return languageMap[ext] || javascript()
}


const Original = CodeMirrorMerge.Original;
const Modified = CodeMirrorMerge.Modified;

const FileSelector = (
    { filePath, setFilePath, file, setFile, hideMerge, setHideMerge, oldFile, setOldFile, repoName }
    : { filePath: string, setFilePath: any, file: string, setFile: any, hideMerge: boolean, setHideMerge: any, oldFile: string, setOldFile: any, repoName: string } ) => {
    const [open, setOpen] = useState(false)
    const [files, setFiles] = useState<{label: string, name: string}[]>([])
    const [value, setValue] = useState("console.log('hello world!');");
    const [isLoading, setIsLoading] = useState(false)
    const placeholderText = "Your code will be displayed here once you select a Repository and file."
    const onChange = useCallback((val: any, viewUpdate: any) => {
        setFile(val)
    }, [setValue, setFile]);

    const onOldChange = useCallback((val: any, viewUpdate: any) => {
        setOldFile(val)
    }, [setValue, setFile]);

    useEffect(() => {
        (async () => {
            let newFiles = await getFiles(repoName)
            console.log(newFiles)
            newFiles = newFiles.map((file: any) => {return {value: file, label: file}})
            setFiles(newFiles)
        })()
    }, [repoName])

    const ext = filePath.split(".").pop() || "js"
    const languageExtension = getLanguage(ext)
    const extensions = [languageExtension, EditorView.lineWrapping]

    return (
        <>
        <Popover open={open} onOpenChange={setOpen}>
            <div className="flex flex-row mb-2">
                <PopoverTrigger asChild>
                    <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={open}
                        className="w-full justify-between mr-2"
                        disabled={!files}
                    >
                        {filePath ? files.find((file: any) => file.value === filePath)?.label : "Select file..."}
                        <CaretSortIcon className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                </PopoverTrigger>
                <Button
                    className="mr-2"
                    variant="secondary"
                    onClick={async () => {
                        setIsLoading(true)
                        await writeFile(repoName, filePath, file)
                        toast.success("File synced to storage!")
                        setIsLoading(false)
                    }}
                    disabled={isLoading || filePath === "" || file === ""}
                >
                    <FaSave /> &nbsp;&nbsp;Save
                </Button>
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
                                    setFilePath(file.value === filePath ? "" : file.value)
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
            <CodeMirror value={file} extensions={extensions} onChange={onChange} theme={vscodeDark} style={{overflow: "auto"}} placeholder={placeholderText}/>
        ): (
            <CodeMirrorMerge theme={vscodeDark} style={{overflow:'auto'}}>
                <Original value={oldFile} extensions={extensions} onChange={onOldChange}/>
                <Modified value={file} extensions={extensions} onChange={onChange}/>
            </CodeMirrorMerge>
        )}
        </>
    )
};

export default FileSelector;
