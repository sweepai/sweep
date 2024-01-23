import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Textarea } from "@/components/ui/textarea";
import React, { useState } from "react";
import FileSelector from "../shared/FileSelector";
import DashboardActions from "./DashboardActions";
import { useLocalStorage } from "usehooks-ts";


const DashboardDisplay = () => {
    const [filePath, setFilePath] = useLocalStorage("filePath", "")
    const [scriptOutput, setScriptOutput] = useLocalStorage("scriptOutput", "")
    const [file, setFile] = useLocalStorage("file", "")
    const [repoName, setRepoName] = useLocalStorage("repoName", '');
    return (
        <ResizablePanelGroup className="min-h-[80vh]" direction="horizontal">
            <ResizablePanel defaultSize={67}>
                <ResizablePanelGroup direction="vertical">
                    <ResizablePanel defaultSize={75} className="flex flex-col mb-4">
                        <FileSelector filePath={filePath} setFilePath={setFilePath} file={file} setFile={setFile} repoName={repoName}></FileSelector>
                    </ResizablePanel>
                    <ResizableHandle withHandle/>
                    <ResizablePanel defaultSize={25}>
                        <Textarea className="mt-4 grow" value={scriptOutput} placeholder="Your script output will be displayed here"></Textarea>
                    </ResizablePanel>
                </ResizablePanelGroup>
                </ResizablePanel>
            <ResizableHandle withHandle/>
            <DashboardActions filePath={filePath} setScriptOutput={setScriptOutput} file={file} setFile={setFile} repoName={repoName} setRepoName={setRepoName} ></DashboardActions>
        </ResizablePanelGroup>
    );
};

export default DashboardDisplay;
