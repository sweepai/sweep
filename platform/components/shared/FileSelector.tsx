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

// const frameworks = [
//     {
//       value: "next.js",
//       label: "Next.js",
//     },
//     {
//       value: "sveltekit",
//       label: "SvelteKit",
//     },
//     {
//       value: "nuxt.js",
//       label: "Nuxt.js",
//     },
//     {
//       value: "remix",
//       label: "Remix",
//     },
//     {
//       value: "astro",
//       label: "Astro",
//     },
// ]

const FileSelector = () => {
    const [open, setOpen] = useState(false)
    const [value, setValue] = useState("")
    const [files, setFiles] = useState([])
    const [file, setFile] = useState("")
    const [value1, setValue1] = React.useState("console.log('hello world!');");
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
                    {value ? files.find((framework) => framework.value === value)?.label : "Select framework..."}
                    <CaretSortIcon className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-full p-0 text-left">
                <Command>
                    <CommandInput placeholder="Search framework..." className="h-9" />
                    <CommandEmpty>No framework found.</CommandEmpty>
                    <CommandGroup>
                        {files.map((framework) => (
                            <CommandItem
                                key={framework.value}
                                value={framework.value}
                                onSelect={async (currentValue) => {
                                    setValue(currentValue === value ? "" : currentValue)
                                    setOpen(false)
                                    setFile((await getFile(framework.value)).contents)
                                }}
                            >
                            {framework.label}
                                <CheckIcon
                                    className={cn(
                                        "ml-auto h-4 w-4",
                                        value === framework.value ? "opacity-100" : "opacity-0"
                                    )}
                                />
                            </CommandItem>
                        ))}
                    </CommandGroup>
                </Command>
            </PopoverContent>
        </Popover>
        <CodeMirror value={file} extensions={[javascript({ jsx: true }), EditorView.lineWrapping]} onChange={onChange} theme={vscodeDark} height="400px"/>
        </>
    )
};

export default FileSelector;