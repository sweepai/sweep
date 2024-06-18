import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { SnippetBadge } from "../shared/SnippetBadge";
import { PullRequest, Snippet } from "@/lib/types";
import { Dispatch, SetStateAction, useState } from "react";
import { ScrollArea } from "../ui/scroll-area";
import { SnippetSearch } from "./SnippetSearch";

const ContextSideBar = ({
  snippets,
  setSnippets,
  repoName,
  branch,
  pulls,
  k,
}: {
  snippets: Snippet[];
  setSnippets: Dispatch<SetStateAction<Snippet[]>>;
  repoName: string;
  branch: string;
  pulls: PullRequest[];
  k: number;
}) => {
  const side = "left"
  const [isOpen, setIsOpen] = useState<boolean>(false)
  return (
    <>
    <div className="grid grid-cols-4 gap-2">
      <Sheet key={side}>
        <SheetTrigger asChild>
          <Button variant="outline" className="fixed left-10 top-1/2 bg-gray-800 text-white vertical-text">Context</Button>
        </SheetTrigger>
        <SheetContent side={side}>
          <SheetHeader className="mb-2">
            <SheetTitle>Current Context</SheetTitle>
            <span>
              <SheetDescription className="w-3/4 inline-block align-middle">
                List of current snippets in context. Run a custom search query to find new snippets.
              </SheetDescription>
              <SnippetSearch  
                snippets={snippets}
                setSnippets={setSnippets} 
                repoName={repoName} 
                branch={branch}  
                pulls={pulls}    
                k={k}        
              />
            </span>
          </SheetHeader>
          <ScrollArea className="h-3/4 w-full rounded-md border">
            {snippets.map((snippet, index) => (
              <SnippetBadge
                key={index}
                snippet={snippet}
                repoName={repoName}
                branch={branch}
                snippets={snippets}
                setSnippets={setSnippets}
                options={["remove"]}
              />
            ))}
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </div>
    </>
  )
}

export { ContextSideBar }
