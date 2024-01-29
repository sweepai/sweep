import { Input } from "../ui/input";
import { ResizablePanel } from "../ui/resizable";
import { Textarea } from "../ui/textarea";
import React, { useEffect, useState } from "react";
import { Button } from "../ui/button";
import getFiles, { getFile, runScript, writeFile } from "../../lib/api.service";
import { toast } from "sonner";
import { FaCheck, FaPen, FaPlay } from "react-icons/fa6";
import { useLocalStorage } from 'usehooks-ts';
import { Label } from "../ui/label";
import { FaArrowsRotate } from "react-icons/fa6";



const DashboardDisplay = ({ filePath, setScriptOutput, file, setFile, hideMerge, setHideMerge, branch, setBranch, oldFile, setOldFile, repoName, setRepoName, setStreamData}
    : { filePath: string, setScriptOutput: any, file: string, setFile: any, hideMerge: boolean, setHideMerge: any, branch: string, setBranch: any, oldFile: any, setOldFile: any, repoName: string, setRepoName: any, setStreamData: any }) => {
    const [script, setScript] = useLocalStorage("script", 'python $FILE_PATH');
    const [instructions, setInstructions] = useLocalStorage("instructions", '');
    const [isLoading, setIsLoading] = useState(false)
    const [currentRepoName, setCurrentRepoName] = useState(repoName);
    const testCasePlaceholder = `Example:
1. Modify the class name to be something more descriptive
2. Add a print statement to the front of each function to describe what each function does.`
    useEffect(() => {
        (async () => {
            const params = new URLSearchParams({repo: repoName}).toString();
            const response = await fetch("/api/branch?" + params)
            const object = await response.json()
            setBranch(object.branch)
        })()
    }, [repoName])

    const updateScript = (event: any) => {
        setScript(event.target.value);
    }
    const updateInstructons = (event: any) => {
        setInstructions(event.target.value);
    }
    const runScriptWrapper = async (newFile: string) => {
        const response = await runScript(repoName, filePath, script, newFile);
        const { code } = response;
        let scriptOutput = response.stdout + "\n" + response.stderr
        if (code != 0) {
            scriptOutput = `Error (exit code ${code}):\n` + scriptOutput
        }
        if (response.code != 0) {
            toast.error("An Error Occured", {
                description: [<div key="stdout">{response.stdout.slice(0, 800)}</div>, <div className="text-red-500" key="stderr">{response.stderr.slice(0, 800)}</div>,]
            })
        } else {
            toast.success("The script ran successfully", {
                description: [<div key="stdout">{response.stdout.slice(0, 800)}</div>, <div key="stderr">{response.stderr.slice(0, 800)}</div>,]
            })
        }
        setScriptOutput(scriptOutput)
    }

    const softIndentationCheck = (oldCode: string, newCode: string, fileContents: string): [string, string] => {
        let newOldCode = oldCode;
        let newNewCode = newCode;
        if (oldCode[0] === '\n') { // expect there to be a newline at the beginning of oldCode
            // find correct indentaton - try up to 16 spaces (8 indentations worth)
            for (let i of [2, 4 ,6 ,8, 10, 12, 14, 16, 18, 20, 22, 24]) {
                // split new code by \n and add the same indentation to each line, then rejoin with new lines
                newOldCode = "\n" + oldCode.split("\n").slice(1).map((line) => " ".repeat(i) + line).join("\n")
                if (fileContents.includes(newOldCode)) {
                    newNewCode = "\n" + newCode.split("\n").slice(1).map((line) => " ".repeat(i) + line).join("\n")
                    break
                }
            }
        }
        return [newOldCode, newNewCode]
    }

    const parseRegexFromOpenAI = (response: string, fileContents: string) => {
        const diffRegex = /<<<<<<< ORIGINAL(\n*?)(?<oldCode>.*?)(\n*?)=======(\n*?)(?<newCode>.*?)(\n*?)>>>>>>> MODIFIED/gs
        //console.log("response:\n", response, "\nend of response\n")
        const diffMatches: any = response.matchAll(diffRegex)!;
        if (!diffMatches) {
            return "";
        }
        var currentFileContents = fileContents;
        for (const diffMatch of diffMatches) {
            let oldCode = diffMatch.groups!.oldCode;
            let newCode = diffMatch.groups!.newCode;
            // soft match indentation, there are cases where openAi will miss indentations
            if (!currentFileContents.includes(oldCode)) {
                const [ newOldCode, newNewCode ] : [string, string] = softIndentationCheck(oldCode, newCode, currentFileContents);
                currentFileContents = currentFileContents.replace(newOldCode, newNewCode)
            } else {
                currentFileContents = currentFileContents.replace(oldCode, newCode)
            }
        }
        return currentFileContents
    }

    const getFileChanges = async () => {
        setStreamData("")
        if (!hideMerge) {
            setOldFile((oldFile: string) => {
                setFile(oldFile)
                return oldFile
            })
            setHideMerge(true)
        }

        setIsLoading(true)
        const url = "/api/openai/edit"
        const body = JSON.stringify({
            fileContents: file.replace(/\\n/g, "\\n"),
            prompt: instructions
        })
        const response = fetch(url, {
            method: "POST",
            body: body
        }).then(async (response) => {
            const reader = response.body!.getReader();
            const decoder = new TextDecoder("utf-8");
            let rawText = String.raw``

            while (true) {
                const { done, value } = await reader?.read();
                if (done) {
                    console.log("STREAM IS FULLY READ")
                    setIsLoading(false)
                    setFile(parseRegexFromOpenAI(rawText, oldFile))
                    break;
                }
                const text = decoder.decode(value);
                rawText += text
                setStreamData((prev: any) => prev + text)
                let updatedFile = parseRegexFromOpenAI(rawText, oldFile);
                //console.log("updated file is:", updatedFile)
                setHideMerge(false)
                setFile(updatedFile);
            }
            setHideMerge(false)
            const changeCount = Math.abs(oldFile.split("\n").length - file.split("\n").length)
            toast.success(`Successfully generated tests!`,{
                description: [<div key="stdout">{`There were ${changeCount} line changes made`}</div>,]}
            )

            if (script) {
                runScriptWrapper(file)
            } else {
                toast.warning("Your Script is empty and will not be run.")
            }
        }).catch((e) => {
            toast.error("An error occured while generating your code.", {description: e})
            setIsLoading(false)
            return
        })
    }

    return (
        <ResizablePanel defaultSize={25} className="p-6 h-[90vh]">
            <div className="flex flex-col h-full">
                <Label className="mb-2">
                    Repository Path
                </Label>
                <Input id="name" placeholder="/Users/sweep/path/to/repo" value={currentRepoName} className="col-span-4 w-full" onChange={(e) => setCurrentRepoName(e.target.value)} onBlur={async () => {
                    try {
                        let newFiles = await getFiles(currentRepoName, 0)
                        toast.success("Successfully fetched files from the repository!")
                        setCurrentRepoName(currentRepoName => {
                            setRepoName(currentRepoName)
                            return currentRepoName
                        })
                    } catch (e) {
                        console.error(e)
                        toast.error("An Error Occured", {
                            description: "Please enter a valid repository name."
                        })
                    }
                }}/>
                <p className="text-sm text-muted-foreground mb-4">
                    Absolute path to your repository.
                </p>
                <Label className="mb-2">
                    Branch
                </Label>
                <Input className="mb-4" value={branch} onChange={e => {
                    setBranch(e.target.value)
                    // TODO: make this work
                }} placeholder="your-branch-here"/>
                <Label className="mb-2">
                    Instructions
                </Label>
                <Textarea id="instructions-input" placeholder={testCasePlaceholder} value={instructions} className="grow mb-4" onChange={updateInstructons}></Textarea>

                <div className="flex flex-row justify-between items-center mt-2">
                    <Label className="mb-2 mr-2">
                        Validation Script
                    </Label>
                    <Button
                        className="mb-2 py-1"
                        variant="secondary"
                        onClick={async () => {
                            setIsLoading(true)
                            await runScriptWrapper(file)
                            setIsLoading(false)
                        }}
                        disabled={isLoading || !script.length}
                    >
                        <FaPlay />&nbsp;&nbsp;Run Tests
                    </Button>
                </div>
                <Textarea id="script-input" placeholder="Enter your script here" className="col-span-4 w-full font-mono" value={script} onChange={updateScript}></Textarea>
                <p className="text-sm text-muted-foreground mb-4">
                    Use $FILE_PATH to refer to the file you selected. E.g. `python $FILE_PATH`.
                </p>
                <div className="flex flex-row justify-center">
                    <Button
                        className="mt-4 mr-4"
                        variant="secondary"
                        onClick={getFileChanges}
                        disabled={isLoading}
                    >
                        <FaPen />&nbsp;&nbsp;Generate Code
                    </Button>
                    <Button
                        className="mt-4 mr-4"
                        variant="secondary"
                        onClick={async () => {
                            setIsLoading(true)
                            const response = await getFile(repoName, filePath)
                            setFile(response.contents)
                            setOldFile(response.contents)
                            toast.success("File synced from storage!")
                            setIsLoading(false)
                            setHideMerge(true)
                        }}
                        disabled={isLoading}
                        >
                        <FaArrowsRotate />&nbsp;&nbsp;Restart
                    </Button>
                    <Button
                        className="mt-4 mr-2 bg-green-600 hover:bg-green-700"
                        onClick={async () => {
                            console.log("oldFile", oldFile)
                            setFile((file: string) => {
                                setOldFile(file)
                                return file
                            })
                            setHideMerge(true)
                            await writeFile(repoName, filePath, file)
                            toast.success("Succesfully saved new file!")
                        }}
                        disabled={isLoading || hideMerge}
                    >
                        <FaCheck />
                    </Button>
                </div>
            </div>
        </ResizablePanel>
    );
};

export default DashboardDisplay;
