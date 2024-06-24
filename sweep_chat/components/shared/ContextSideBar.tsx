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
import { HoverCard, HoverCardContent, HoverCardTrigger } from '../ui/hover-card'
import { FaInfoCircle } from 'react-icons/fa'
import PulsingLoader from './PulsingLoader'

const ContextSideBar = ({
  snippets,
  setSnippets,
  repoName,
  branch,
  k,
  searchMessage,
}: {
  snippets: Snippet[]
  setSnippets: Dispatch<SetStateAction<Snippet[]>>
  repoName: string
  branch: string
  k: number
  searchMessage: string
}) => {
  return (
    <div className="h-full w-full flex flex-col">
      <div className="pb-2 pl-2">
        <h2 className="text-lg font-bold mb-2 flex items-center">
          Context
          <HoverCard>
            <HoverCardTrigger>
              <FaInfoCircle className="text-gray-400 hover:text-gray-200 hover:cursor-pointer ml-2" />
            </HoverCardTrigger>
            <HoverCardContent>
              <p className="text-sm text-gray-300">
                List of current snippets in context. Run a custom search query
                to find new snippets.
              </p>
            </HoverCardContent>
          </HoverCard>
        </h2>
      </div>
      <ScrollArea className="w-full rounded-md border p-4 grow mb-4 overflow-x-auto">
        {searchMessage && (
          <div className="flex flex-col justify-center items-center">
            <p className="text-gray-500 center mb-4">{searchMessage}</p>
            <div>
              <PulsingLoader size={1} />
            </div>
          </div>
        )}
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
