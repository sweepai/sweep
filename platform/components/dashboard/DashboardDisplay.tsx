import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Textarea } from "@/components/ui/textarea";
import React, { useState } from "react";
import FileSelector from "../shared/FileSelector";
import DashboardActions from "./DashboardActions";
import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";


const DashboardDisplay = () => {
    const [oldFile, setOldFile] = useLocalStorage("oldFile", "")
    const [hideMerge, setHideMerge] = useLocalStorage("hideMerge", true)
    const [branch, setBranch] = useLocalStorage("branch", "");
    const [filePath, setFilePath] = useLocalStorage("filePath", "")
    const [scriptOutput, setScriptOutput] = useLocalStorage("scriptOutput", "")
    const [file, setFile] = useLocalStorage("file", "");
    const [repoName, setRepoName] = useLocalStorage("repoName", '');
    console.log("file", file)
    return (
        <>
        <h1 className="font-bold text-xl">Sweep Unit Test Generator</h1>
        <ResizablePanelGroup className="min-h-[80vh] pt-0" direction="horizontal">
            <DashboardActions filePath={filePath} setScriptOutput={setScriptOutput}
            file={file} setFile={setFile} hideMerge={hideMerge}
            setHideMerge={setHideMerge} oldFile={oldFile} setOldFile={setOldFile}
            repoName={repoName} setRepoName={setRepoName}></DashboardActions>
            <ResizableHandle withHandle/>
            <ResizablePanel defaultSize={75}>
                <ResizablePanelGroup direction="vertical">
                    <ResizablePanel defaultSize={75} className="flex flex-col mb-4">
                        <FileSelector filePath={filePath} setFilePath={setFilePath}
                        file={file} setFile={setFile} hideMerge={hideMerge} setHideMerge={setHideMerge}
                        oldFile={oldFile} setOldFile={setOldFile} repoName={repoName}></FileSelector>
                    </ResizablePanel>
                    <ResizableHandle withHandle/>
                    <ResizablePanel defaultSize={25}>
                        <Label className="mb-2">
                            Test Output
                        </Label>
                        {/* <Button onClick={() => {
                            setHideMerge(!hideMerge)
                        }}>Toggle</Button> */}
                        <Textarea className={`mt-4 grow font-mono h-[200px] ${scriptOutput.trim().startsWith("Error") ? "text-red-600": "text-green-600"}`} value={scriptOutput.trim()} placeholder="Your script output will be displayed here" readOnly></Textarea>
                    </ResizablePanel>
                </ResizablePanelGroup>
            </ResizablePanel>      
        </ResizablePanelGroup>
        </>
    );
};

export default DashboardDisplay;
