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
  return (
    <div className="h-full w-full flex flex-col">
      <div className='p-4'>
        <h2 className='text-lg font-bold mb-2'>Current Context</h2>
        <p className="text-sm text-gray-300">
          List of current snippets in context. Run a custom search query
          to find new snippets.
        </p>
      </div>
      <ScrollArea className="w-full rounded-md border p-4 grow mb-4">
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
      <SnippetSearch
        snippets={snippets}
        setSnippets={setSnippets}
        repoName={repoName}
        branch={branch}
        k={k}
      />
    </div>
  )
}

export { ContextSideBar }
