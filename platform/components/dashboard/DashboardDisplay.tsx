import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "../ui/resizable";
import { Textarea } from "../ui/textarea";
import React, { useEffect, useState } from "react";
import FileSelector from "../shared/FileSelector";
import DashboardActions from "./DashboardActions";
import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { Button } from "../ui/button";


const DashboardDisplay = () => {
    const [oldFile, setOldFile] = useLocalStorage("oldFile", "")
    const [hideMerge, setHideMerge] = useLocalStorage("hideMerge", true)
    const [branch, setBranch] = useLocalStorage("branch", "");
    const [streamData, setStreamData] = useState("");
    const [outputToggle, setOutputToggle] = useState("script");
    const [filePath, setFilePath] = useLocalStorage("filePath", "")
    const [scriptOutput, setScriptOutput] = useLocalStorage("scriptOutput", "")
    const [file, setFile] = useLocalStorage("file", "");
    const [repoName, setRepoName] = useLocalStorage("repoName", '');

    useEffect(() => {
        let textarea = document.getElementById("llm-output") as HTMLTextAreaElement;
        textarea.scrollTop = textarea.scrollHeight;
    }, [streamData])
    return (
        <>
        <h1 className="font-bold text-xl">Sweep Assistant</h1>
        <ResizablePanelGroup className="min-h-[80vh] pt-0" direction="horizontal">
            <DashboardActions filePath={filePath} setScriptOutput={setScriptOutput}
            file={file} setFile={setFile} hideMerge={hideMerge}
            setHideMerge={setHideMerge} branch={branch} setBranch={setBranch} oldFile={oldFile} setOldFile={setOldFile}
            repoName={repoName} setRepoName={setRepoName} setStreamData={setStreamData}></DashboardActions>
            <ResizableHandle withHandle/>
            <ResizablePanel defaultSize={75}>
                <ResizablePanelGroup direction="vertical">
                    <ResizablePanel defaultSize={75} className="flex flex-col mb-4">
                        <FileSelector filePath={filePath} setFilePath={setFilePath}
                            file={file} setFile={setFile} hideMerge={hideMerge} setHideMerge={setHideMerge}
                            oldFile={oldFile} setOldFile={setOldFile} repoName={repoName}></FileSelector>
                    </ResizablePanel>
                    <ResizableHandle withHandle/>
                    <ResizablePanel className="mt-2" defaultSize={25}>
                        <Label className="mb-2 mr-2">
                            Toggle between outputs:
                        </Label>
                        <Button
                            className="mr-2"
                            variant="secondary"
                            onClick={() => {
                                setOutputToggle("script")
                                console.log(outputToggle)
                            }}>
                            Validation Output
                        </Button>
                        <Button
                            variant="secondary"
                            onClick={() => {
                                setOutputToggle("llm")
                                console.log(outputToggle)
                            }}>
                            GPT Debug Logs
                        </Button>
                        <Textarea className={`mt-4 grow font-mono h-[200px] ${scriptOutput.trim().startsWith("Error") ? "text-red-600": "text-green-600"}`} value={scriptOutput.trim()} id="script-output" placeholder="Your script output will be displayed here" readOnly hidden={outputToggle !== "script"}></Textarea>
                        <Textarea className={`mt-4 grow font-mono h-[200px] `} id="llm-output" value={streamData} placeholder="GPT will display what it is thinking here." readOnly hidden={outputToggle!== "llm"}></Textarea>
                    </ResizablePanel>
                </ResizablePanelGroup>
            </ResizablePanel>
        </ResizablePanelGroup>
        </>
    );
};

export default DashboardDisplay;
