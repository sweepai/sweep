
import { Input } from "@/components/ui/input";
import { ResizablePanel } from "@/components/ui/resizable";
import { Textarea } from "@/components/ui/textarea";
import React, { useEffect, useState } from "react";
import { Button } from "../ui/button";
import getFiles, { getFile, runScript, writeFile } from "@/lib/api.service";
import { toast } from "sonner";
import { FaCheck, FaPen, FaPlay } from "react-icons/fa6";
import { useLocalStorage } from 'usehooks-ts';
import { Label } from "../ui/label";
import { FaArrowsRotate } from "react-icons/fa6";



const DashboardDisplay = ({ filePath, setScriptOutput, file, setFile, hideMerge, setHideMerge, oldFile, setOldFile, repoName, setRepoName}
    : { filePath: string, setScriptOutput: any, file: string, setFile: any, hideMerge: boolean, setHideMerge: any, oldFile: any, setOldFile: any, repoName: string, setRepoName: any }) => {
    const [script, setScript] = useLocalStorage("script", 'python $FILE_PATH');
    const [instructions, setInstructions] = useLocalStorage("instructions", '');
    const [isLoading, setIsLoading] = useState(false)
    const [branch, setBranch] = useState("");
    const [currentRepoName, setCurrentRepoName] = useState(repoName);
    const testCasePlaceholder = `Example:
Add a unit test that checks for a bad postgres connection:

def get_data(conn):
"""Retrieves data from the PostgreSQL database using a given connection."""
try:
    cur = conn.cursor()
    cur.execute("SELECT * FROM example_table")
    records = cur.fetchall()
    cur.close()
    return records
except Exception as e:
    print(f"Error retrieving data: {e}")
    return []`
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
    const getFileChanges = async () => {
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
        const response = await fetch(url, {
            method: "POST",
            body: body
        })
        const object = await response.json();
        setIsLoading(false)
        if (!object.newFileContents || object.newFileContents === file) {
            toast.error("An error occured while generating your code.", {description: "Please try again"})
            return
        }
        setFile(object.newFileContents)
        setHideMerge(false)
        const changeCount = Math.abs(oldFile.split("\n").length - object.newFileContents.split("\n").length)
        toast.success(`Successfully generated tests!`,
        {
            description: [<div key="stdout">{`There were ${changeCount} line changes made`}</div>,]
        } )
        if (script) { 
            runScriptWrapper(object.newFileContents)
        } else {
            toast.warning("Your Script is empty and will not be run.")
        }
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
                <Input className="mb-4" value={branch} placeholder="your-branch-here"/>
                <Label className="mb-2">
                    Instructions
                </Label>
                <Textarea id="instructions-input" placeholder={testCasePlaceholder} value={instructions} className="grow mb-4" onChange={updateInstructons}></Textarea>
                
                <div className="flex flex-row justify-between items-center mt-2">
                    <Label className="mb-2 mr-2">
                        Test Script
                    </Label>
                    <Button
                        className="mb-2 py-1"
                        variant="secondary"
                        onClick={() => {
                            runScriptWrapper(file)
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
                        <FaArrowsRotate />&nbsp;&nbsp;Refresh
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
