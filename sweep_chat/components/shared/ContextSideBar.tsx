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
import { Snippet } from "@/lib/types";
import { Dispatch, SetStateAction } from "react";

const ContextSideBar = ({
  snippets,
  setSnippets,
  repoName,
  branch,
}: {
  snippets: Snippet[];
  setSnippets: Dispatch<SetStateAction<Snippet[]>>;
  repoName: string;
  branch: string;
}) => {
  const side = "left"
  return (
    <div className="grid grid-cols-4 gap-2">
      <Sheet key={side}>
        <SheetTrigger asChild>
          <Button variant="outline" className="fixed left-0 top-1/2 bg-gray-800 text-white">Context</Button>
        </SheetTrigger>
        <SheetContent side={side} className="w-full">
          <SheetHeader>
            <SheetTitle>Current Context</SheetTitle>
            <SheetDescription>
              List of current snippets in context. Add and remove them as you see fit.
            </SheetDescription>
          </SheetHeader>
          {snippets.map((snippet, index) => (
            <SnippetBadge
              key={index}
              snippet={snippet}
              repoName={repoName}
              branch={branch}
              snippets={snippets}
              setSnippets={setSnippets}
            />
          ))}
        </SheetContent>
      </Sheet>
    </div>
  )
}

export { ContextSideBar }
