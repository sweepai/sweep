
import { Input } from "@/components/ui/input";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Textarea } from "@/components/ui/textarea";
import React, { useEffect } from "react";
import { Button } from "../ui/button";
import FileSelector from "../shared/FileSelector";
import DashboardSettings from "./DashboardSettings";


const DashboardDisplay = () => {
    const [value, setValue] = React.useState("console.log('hello world!');");
    const [branch, setBranch] = React.useState("");
    useEffect(() => {
        (async () => {
            const params = new URLSearchParams({repo: "/home/kevin/sweep"}).toString();
            const response = await fetch("/api/branch?" + params)
            const object = await response.json()
            setBranch(object.branch)
        })()
    }, [])
    return (
        <ResizablePanelGroup className="min-h-[80vh]" direction="horizontal">
            <ResizablePanel defaultSize={67}>
                <ResizablePanelGroup direction="vertical">
                    <ResizablePanel defaultSize={75} className="flex flex-col mb-4">
                        <FileSelector></FileSelector>
                    </ResizablePanel>
                    <ResizableHandle withHandle/>
                    <ResizablePanel defaultSize={25}>
                        <Textarea className="mt-4 grow"> Put info in here</Textarea>
                    </ResizablePanel>
                </ResizablePanelGroup>
                </ResizablePanel>
            <ResizableHandle withHandle/>
            <ResizablePanel defaultSize={33} className="p-6 h-[80vh]">
                <div className="flex flex-col h-full">
                    <Input
                        className="mb-4"
                        value={branch}
                        onChange={(e: any) => {
                        setBranch(e.target.value)
                    }}/>
                    <Textarea placeholder="Edge cases for Sweep to cover." className="grow"></Textarea>
                    <div className="flex flex-row justify-center">
                        <DashboardSettings></DashboardSettings>
                        <Button className="mt-4 mr-4" variant="secondary">Generate tests</Button>
                        <Button className="mt-4" variant="secondary">Run tests</Button>
                    </div>
                </div>
            </ResizablePanel>
        </ResizablePanelGroup>
    );
};

export default DashboardDisplay;
