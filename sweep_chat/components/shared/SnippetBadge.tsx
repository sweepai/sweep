import { typeNameToColor, codeStyle } from '@/lib/constants'
import { sliceLines } from '@/lib/str_utils'
import { Snippet } from '@/lib/types'
import {
  HoverCard,
  HoverCardTrigger,
  HoverCardContent,
} from '@/components/ui/hover-card'
import { FaTrash, FaPlus } from 'react-icons/fa'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { Button } from '../ui/button'
import { Dispatch, SetStateAction } from 'react'

const snippetIsEqual = ({
  snippetOne,
  snippetTwo,
}: {
  snippetOne: Snippet
  snippetTwo: Snippet
}) => {
  return (
    snippetOne.content == snippetTwo.content &&
    snippetOne.file_path == snippetTwo.file_path &&
    snippetOne.end == snippetTwo.end &&
    snippetOne.start == snippetTwo.start
  )
}

const RenderPath = ({
  snippet,
  snippets,
  newSnippets,
  setSnippets,
  setNewSnippets,
  options,
  repoName,
  branch,
}: {
  snippet: Snippet
  snippets: Snippet[]
  newSnippets?: Snippet[]
  setSnippets: Dispatch<SetStateAction<Snippet[]>>
  setNewSnippets?: Dispatch<SetStateAction<Snippet[]>>
  options: string[]
  repoName: string
  branch: string
}) => {
  let path = snippet.file_path
  let truncatedPath = path
  const maxPathLength = 100
  if (path.length > maxPathLength) {
    truncatedPath = '...' + path.slice((maxPathLength - 3) * -1)
  }
  return (
    <span>
      <span className="inline-block align-middle">
        {options.includes('remove') ? (
          <FaTrash
            className="mr-2 hover:drop-shadow-md hover:text-gray-400"
            onClick={() => {
              let newSnippets = []
              for (let curSnippet of snippets) {
                if (
                  !snippetIsEqual({
                    snippetOne: snippet,
                    snippetTwo: curSnippet,
                  })
                ) {
                  newSnippets.push(curSnippet)
                }
              }
              setSnippets(newSnippets)
            }}
          />
        ) : (
          <></>
        )}
        {options.includes('add') ? (
          <FaPlus
            className="mr-2 hover:drop-shadow-md hover:text-gray-300"
            onClick={() => {
              let tempSnippets = [...snippets]
              // if we are adding a snippet that means the score should be 1
              snippet.score = 1
              tempSnippets.push(snippet)
              setSnippets(tempSnippets)
              // remove the snippets from newSnippets
              if (setNewSnippets && newSnippets) {
                let tempNewSnippets = []
                for (let curSnippet of newSnippets) {
                  if (
                    !snippetIsEqual({
                      snippetOne: snippet,
                      snippetTwo: curSnippet,
                    })
                  ) {
                    tempNewSnippets.push(curSnippet)
                  }
                }
                setNewSnippets(tempNewSnippets)
              }
            }}
          />
        ) : (
          <></>
        )}
      </span>
      <span
        onClick={() => {
          window.open(
            `https://github.com/${repoName}/blob/${branch}/${snippet.file_path}`,
            '_blank'
          )
        }}
      >
        <div className="text-white inline-block align-middle mr-2">
          {truncatedPath.substring(truncatedPath.lastIndexOf('/') + 1)}
        </div>
        <div className="text-gray-400 inline-block align-middle">
          {truncatedPath}
        </div>
      </span>
      {!(
        snippet.end > snippet.content.split('\n').length - 3 &&
        snippet.start == 0
      ) && (
        <span className="text-gray-400 inline-block align-middle">
          :{snippet.start}-{snippet.end}
        </span>
      )}
      {snippet.type_name !== 'source' && (
        <code className="ml-2 bg-opacity-20 bg-black text-white rounded p-1 px-2 text-xs">
          {snippet.type_name}
        </code>
      )}
    </span>
  )
}

const getLanguage = (filePath: string) => {
  return filePath.split('.').pop()
}

const SnippetBadge = ({
  snippet,
  className,
  repoName,
  branch,
  button,
  snippets,
  newSnippets,
  setSnippets,
  setNewSnippets,
  options,
}: {
  snippet: Snippet
  className?: string
  repoName: string
  branch: string
  button?: JSX.Element
  snippets: Snippet[]
  newSnippets?: Snippet[]
  setSnippets: Dispatch<SetStateAction<Snippet[]>>
  setNewSnippets?: Dispatch<SetStateAction<Snippet[]>>
  options: string[]
}) => {
  return (
    <HoverCard openDelay={300} closeDelay={200}>
      <div
        className={`p-2 rounded-xl mb-2 text-xs inline-block mr-2 ${
          typeNameToColor[snippet.type_name]
        } ${className || ''} `}
        style={{ opacity: `${Math.max(Math.min(1, snippet.score), 0.5)}` }}
      >
        <HoverCardTrigger asChild>
          <Button variant="link" className="text-sm py-0 px-1 h-6 leading-4">
            <span>
              <RenderPath
                snippet={snippet}
                snippets={snippets}
                newSnippets={newSnippets}
                setSnippets={setSnippets}
                setNewSnippets={setNewSnippets}
                options={options}
                repoName={repoName}
                branch={branch}
              />
            </span>
          </Button>
        </HoverCardTrigger>
      </div>
      <HoverCardContent className="w-[800px] mr-2" style={{ opacity: 1 }}>
        <SyntaxHighlighter
          PreTag="div"
          language={getLanguage(snippet.file_path)}
          style={codeStyle}
          customStyle={{
            backgroundColor: 'transparent',
            whiteSpace: 'pre-wrap',
          }}
          className="rounded-xl max-h-[600px] overflow-y-auto p-4 w-full"
        >
          {sliceLines(snippet.content, snippet.start, snippet.end)}
        </SyntaxHighlighter>
      </HoverCardContent>
    </HoverCard>
  )
}

export { SnippetBadge }
