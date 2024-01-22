import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import Image from "next/image";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24">
      <ResizablePanelGroup className="min-h-[80vh]" direction="horizontal">
        <ResizablePanel defaultSize={67}>
          <ResizablePanelGroup direction="vertical">
            <ResizablePanel defaultSize={75} className="flex flex-col mb-4">
              <Select>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="File path" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="light">Light</SelectItem>
                  <SelectItem value="dark">Dark</SelectItem>
                  <SelectItem value="system">System</SelectItem>
                </SelectContent>
              </Select>
              <Textarea className="mt-4 grow">
                File content
              </Textarea>
            </ResizablePanel>
            <ResizableHandle withHandle/>
            <ResizablePanel defaultSize={25}>
              <Textarea className="mt-4">
                Terminal
              </Textarea>
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
        <ResizableHandle withHandle/>
        <ResizablePanel defaultSize={33} className="p-6 h-[80vh]">
          <div className="flex flex-col h-full">
            <Input className="mb-4" value="sweep/fix-branch"/>
            <Textarea placeholder="Edge cases for Sweep to cover." className="grow"></Textarea>
            <div className="flex flex-row justify-center">
              <Button className="mt-4 mr-4" variant="secondary">Generate tests</Button>
              <Button className="mt-4" variant="secondary">Run tests</Button>
            </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </main>
  );
}
