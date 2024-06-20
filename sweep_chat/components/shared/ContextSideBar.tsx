import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { SnippetBadge } from '../shared/SnippetBadge'
import { PullRequest, Snippet } from '@/lib/types'
import { Dispatch, SetStateAction, useState } from 'react'
import { ScrollArea } from '../ui/scroll-area'
import { SnippetSearch } from './SnippetSearch'

const ContextSideBar = ({
  snippets,
  setSnippets,
  repoName,
  branch,
  k,
}: {
  snippets: Snippet[]
  setSnippets: Dispatch<SetStateAction<Snippet[]>>
  repoName: string
  branch: string
  k: number
}) => {
  const side = 'left'
  return (
    <>
      <div className="grid grid-cols-4 gap-2">
        <Sheet key={side}>
          <SheetTrigger asChild>
            <Button
              variant="outline"
              className="fixed left-10 top-1/2 px-6 text-white vertical-text text-lg bg-blue-900 hover:bg-blue-800"
            >
              Manage Context
            </Button>
          </SheetTrigger>
          <SheetContent side={side} className="w-full flex flex-col">
            <SheetHeader>
              <SheetTitle>Current Context</SheetTitle>
              <div className="flex justify-between align-middle">
                <SheetDescription className="w-3/4 inline-block align-middle my-auto">
                  List of current snippets in context. Run a custom search query
                  to find new snippets.
                </SheetDescription>
                <SnippetSearch
                  snippets={snippets}
                  setSnippets={setSnippets}
                  repoName={repoName}
                  branch={branch}
                  k={k}
                />
              </div>
            </SheetHeader>
            <ScrollArea className="h-3/4 w-full rounded-md border p-4 grow">
              {snippets.map((snippet, index) => (
                <>
                  <SnippetBadge
                    key={index}
                    snippet={snippet}
                    repoName={repoName}
                    branch={branch}
                    snippets={snippets}
                    setSnippets={setSnippets}
                    options={['remove']}
                  />
                  <br />
                </>
              ))}
            </ScrollArea>
          </SheetContent>
        </Sheet>
      </div>
    </>
  )
}

export { ContextSideBar }
