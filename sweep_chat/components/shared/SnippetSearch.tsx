import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

import { SnippetBadge } from '../shared/SnippetBadge'
import { Message, PullRequest, Snippet } from '@/lib/types'
import { Dispatch, SetStateAction, useState } from 'react'
import { ScrollArea } from '../ui/scroll-area'
import { toast } from '../ui/use-toast'
import { posthog } from '@/lib/posthog'
import { streamMessages } from '@/lib/streamingUtils'
import { useSession } from 'next-auth/react'
import { Session } from 'next-auth'
import PulsingLoader from './PulsingLoader'
import { FaSearchPlus } from 'react-icons/fa'

const SnippetSearch = ({
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
  const [newSnippets, setNewSnippets] = useState<Snippet[]>([])
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [searchIsLoading, setSearchIsLoading] = useState<boolean>(false)
  const [progressMessage, setProgressMessage] = useState<string>('')
  const { data: session } = useSession()

  const searchForSnippets = async () => {
    setSearchIsLoading(true)
    setNewSnippets([])
    // We purposefully do not include any pull information as this tends to bias the search
    // Subject to change
    const annotations = { pulls: [] }
    // execute a search
    try {
      const snippetsResponse = await fetch(`/backend/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // @ts-ignore
          Authorization: `Bearer ${session?.user.accessToken}`,
        },
        body: JSON.stringify({
          repo_name: repoName,
          query: searchQuery,
          annotations: annotations,
        }),
      })
      let currentSnippets: Snippet[] = []
      const reader = snippetsResponse.body?.getReader()!
      for await (const chunk of streamMessages(reader)) {
        let streamedMessage = chunk[0]
        setProgressMessage(streamedMessage)
        currentSnippets = chunk[1]
        currentSnippets = currentSnippets.slice(0, k)
        if (currentSnippets) {
          setNewSnippets(currentSnippets)
        }
      }
      if (!currentSnippets.length) {
        throw new Error('No snippets found')
      }
      setSearchIsLoading(false)
    } catch (e: any) {
      console.log(e)
      toast({
        title: 'Failed to search codebase',
        description: `The following error has occurred: ${e.message}. Sometimes, logging out and logging back in can resolve this issue.`,
        variant: 'destructive',
        duration: Infinity,
      })
      posthog.capture('SnippetSearch errored', {
        repoName,
        newSnippets,
        error: e.message,
      })
      setSearchIsLoading(true)
      throw e
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      // Call searchForSnippets when Enter key is pressed
      searchForSnippets()
    }
  }
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">
          <FaSearchPlus className="mr-2" />
          Add Snippets
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-9/10 p-8">
        <DialogHeader>
          <DialogTitle>Search Repo</DialogTitle>
          <DialogDescription>
            Make a custom search to fetch relevant snippets that you can choose
            to add to the context
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="items-center gap-4 flex flex-row">
            <Input
              id="username"
              placeholder="Custom Search Query"
              className="grow"
              onInput={(event: React.ChangeEvent<HTMLInputElement>) => {
                setSearchQuery(event.target.value)
              }}
              onKeyDown={handleKeyDown}
            />
            <Button
              className="text-white bg-blue-900 hover:bg-blue-800 w-fit"
              disabled={searchQuery.length == 0 || searchIsLoading}
              onClick={searchForSnippets}
            >
              {searchIsLoading ? 'Searching...' : 'Search'}
            </Button>
          </div>
        </div>
        {searchIsLoading && (
          <div className="flex flex-col justify-center items-center mb-4">
            <p className="text-gray-500 center mb-4">{progressMessage}</p>
            <div>
              <PulsingLoader size={1} />
            </div>
          </div>
        )}
        {newSnippets.length > 0 && (
          <ScrollArea className="h-full w-full rounded-md border mb-6 p-4">
            {newSnippets.map((snippet, index) => (
              <SnippetBadge
                key={index}
                snippet={snippet}
                repoName={repoName}
                branch={branch}
                snippets={snippets}
                setSnippets={setSnippets}
                setNewSnippets={setNewSnippets}
                newSnippets={newSnippets}
                options={['add']}
              />
            ))}
          </ScrollArea>
        )}
        <DialogFooter></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export { SnippetSearch }
