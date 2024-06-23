import {
    HoverCard,
    HoverCardContent,
    HoverCardTrigger,
} from '@/components/ui/hover-card'

import { Message, PullRequest, StatefulCodeSuggestion } from '@/lib/types'
import { useState, useEffect, useRef, useMemo } from 'react'
import { FaPencilAlt, FaCheck, FaPlus, FaChevronDown, FaChevronUp, FaExclamationTriangle, FaPaperPlane } from 'react-icons/fa'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { CODE_CHANGE_PATTERN, MarkdownRenderer } from '@/components/shared/MarkdownRenderer'
import { codeStyle, languageMapping, roleToColor } from '@/lib/constants'
import { getFunctionCallHeaderString, truncate } from '@/lib/str_utils'
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@radix-ui/react-accordion'
import SyntaxHighlighter from 'react-syntax-highlighter'
import CodeMirrorEditor from './CodeMirrorSuggestionEditor'
import FeedbackBlock from './FeedbackBlock'
import PrValidationStatusesDisplay from './PrValidationStatusesDisplay'
import PullRequestDisplay from './PullRequestDisplay'
import PulsingLoader from './shared/PulsingLoader'
import { SnippetBadge } from './shared/SnippetBadge'

// @ts-ignore
import * as Diff from 'diff'

const UserMessageDisplay = ({
  message,
  onEdit,
}: {
  message: Message
  onEdit: (content: string) => void
}) => {
  const [isEditing, setIsEditing] = useState(false)
  const [editedContent, setEditedContent] = useState(message.content)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleClick = () => {
    setIsEditing(true)
  }

  const handleBlur = () => {
    setIsEditing(false)
  }

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [editedContent, textareaRef])

  return (
    <>
      <div className="flex justify-end">
        {!isEditing && (
          <FaPencilAlt
            className="inline-block text-zinc-400 mr-2 mt-3 hover:cursor-pointer hover:text-zinc-200 hover:drop-shadow-md"
            onClick={handleClick}
          />
        )}
        &nbsp;
        <div
          className="bg-zinc-800 transition-color text-sm p-3 rounded-xl mb-4 inline-block max-w-[80%] hover:bg-zinc-700 hover:cursor-pointer text-left"
          onClick={handleClick}
        >
          <div className={`text-sm text-white`}>
            {isEditing ? (
              <Textarea
                className="w-full mb-4 bg-transparent text-white max-w-[800px] w-[800px] hover:bg-initial"
                ref={textareaRef}
                value={editedContent}
                onChange={(e) => {
                  setEditedContent(e.target.value)
                  e.target.style.height = 'auto'
                  e.target.style.height = `${e.target.scrollHeight}px`
                }}
                style={{ height: (editedContent.split('\n').length + 1) * 16 }}
                autoFocus
              />
            ) : (
              <MarkdownRenderer
                content={message.content.trim()}
                className="userMessage"
              />
            )}
          </div>
          {isEditing && (
            <>
              <Button
                onClick={(e) => {
                  handleBlur()
                  e.stopPropagation()
                  e.preventDefault()
                }}
                variant="secondary"
                className="bg-zinc-800 text-white"
              >
                Cancel
              </Button>
              <Button
                onClick={(e) => {
                  onEdit(editedContent)
                  setIsEditing(false)
                  handleBlur()
                  e.stopPropagation()
                  e.preventDefault()
                }}
                variant="default"
                className="ml-2 bg-blue-900 text-white hover:bg-blue-800"
              >
                <FaPaperPlane />
                  &nbsp;&nbsp;Send
              </Button>
            </>
          )}
        </div>
      </div>
      {!isEditing &&
        message.annotations?.pulls?.map((pr) => (
          <div className="flex justify-end text-sm" key={pr.number}>
            <PullRequestDisplay pr={pr} />
          </div>
        ))}
    </>
  )
}

export default function MessageDisplay({
  message,
  className,
  onEdit,
  repoName,
  branch,
  commitToPR,
  setSuggestedChanges,
  onValidatePR,
  fixPrValidationErrors,
  index,
}: {
  message: Message
  className?: string
  onEdit: (content: string) => void
  repoName: string
  branch: string
  commitToPR: boolean
  setSuggestedChanges: React.Dispatch<
    React.SetStateAction<StatefulCodeSuggestion[]>
  >
  onValidatePR?: (pr: PullRequest) => void
  fixPrValidationErrors: () => void
  index: number
}) {
  const [collapsedArray, setCollapsedArray] = useState<boolean[]>(
    message.annotations?.codeSuggestions?.map(() => false) || []
  )
  const codeMirrors = useMemo(() => {
    return (
      message.annotations?.codeSuggestions?.map((suggestion) => (
        <CodeMirrorEditor
          suggestion={suggestion}
          index={index}
          setSuggestedChanges={setSuggestedChanges}
          key={index}
        />
      )) || []
    )
  }, [message.annotations?.codeSuggestions, collapsedArray])
  if (message.role === 'user') {
    return <UserMessageDisplay message={message} onEdit={onEdit} />
  }
  let matches = Array.from(message.content.matchAll(CODE_CHANGE_PATTERN))
  if (matches.some((match) => !match.groups?.closingTag)) {
    matches = []
  }
  return (
    <>
      <div className={`flex justify-start`}>
        {(!message.annotations?.pulls ||
          message.annotations!.pulls?.length == 0) && (
          <div
            className={`transition-color text-sm p-3 rounded-xl mb-4 inline-block max-w-[80%] text-left w-[80%]
              ${message.role === 'assistant' ? 'py-1' : ''} ${
                className || roleToColor[message.role]
              }`}
          >
            {message.role === 'function' ? (
              <Accordion
                type="single"
                collapsible
                className="w-full"
                // include defaultValue if there we want a message to be default open
                // defaultValue={((message.content && message.function_call?.function_name === "search_codebase") || (message.function_call?.snippets?.length !== undefined && message.function_call?.snippets?.length > 0)) ? "function" : undefined}
              >
                <AccordionItem value="function" className="border-none">
                  <AccordionTrigger className="border-none py-0 text-left">
                    <div className="text-xs text-gray-400 flex align-center">
                      {!message.function_call!.is_complete ? (
                        <PulsingLoader size={0.5} />
                      ) : (
                        <FaCheck
                          className="inline-block mr-2"
                          style={{ marginTop: 2 }}
                        />
                      )}
                      <span>
                        {getFunctionCallHeaderString(message.function_call)}
                      </span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent
                    className={`pb-0 ${
                      message.content &&
                      message.function_call?.function_name ===
                        'search_codebase' &&
                      !message.function_call?.is_complete
                        ? 'pt-6'
                        : 'pt-0'
                    }`}
                  >
                    {message.function_call?.function_name ===
                      'search_codebase' &&
                      message.content &&
                      !message.function_call.is_complete && (
                        <span className="p-4 pl-2">{message.content}</span>
                      )}
                    {message.function_call!.snippets ? (
                      <div className="pb-0 pt-4">
                        {message.function_call!.snippets.map(
                          (snippet, index) => (
                            <SnippetBadge
                              key={index}
                              snippet={snippet}
                              className=""
                              repoName={repoName}
                              branch={branch}
                              button={<></>}
                              snippets={[]}
                              setSnippets={() => {}}
                              newSnippets={[]}
                              setNewSnippets={() => {}}
                              options={[]}
                            />
                          )
                        )}
                      </div>
                    ) : message.function_call!.function_name ===
                        'self_critique' ||
                      message.function_call!.function_name === 'analysis' ? (
                      <MarkdownRenderer
                        content={message.content}
                        className="reactMarkdown mt-4 mb-0 py-0"
                      />
                    ) : (
                      <SyntaxHighlighter
                        language="xml"
                        style={codeStyle}
                        customStyle={{
                          backgroundColor: 'transparent',
                          whiteSpace: 'pre-wrap',
                          maxHeight: '300px',
                        }}
                        className="rounded-xl p-4"
                      >
                        {message.content}
                      </SyntaxHighlighter>
                    )}
                    <FeedbackBlock message={message} index={index} />
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            ) : message.role === 'assistant' ? (
              <>
                <MarkdownRenderer
                  content={message.content}
                  className="reactMarkdown mb-0 py-2"
                />
                <FeedbackBlock message={message} index={index} />
              </>
            ) : (
              <UserMessageDisplay message={message} onEdit={onEdit} />
            )}
          </div>
        )}
      </div>
      {message.annotations?.pulls?.map((pr) => (
        <div className="flex justify-start text-sm" key={pr.number}>
          <PullRequestDisplay pr={pr} onValidatePR={onValidatePR} />
        </div>
      ))}
      {message.annotations?.prValidationStatuses &&
        message.annotations?.prValidationStatuses.length > 0 && (
          <PrValidationStatusesDisplay
            statuses={message.annotations?.prValidationStatuses}
            fixPrValidationErrors={fixPrValidationErrors}
          />
        )}
      {message.annotations?.codeSuggestions &&
        message.annotations?.codeSuggestions.length > 0 && (
          <div className="text-sm max-w-[80%] p-4 rounded bg-zinc-700 space-y-4 mb-4">
            <div className="flex justify-between items-center">
              <h2 className="font-bold">Suggested Changes</h2>
              {message.annotations?.codeSuggestions?.length > 1 && (
                <Button
                  className="bg-green-800 hover:bg-green-700 text-white"
                  size="sm"
                  onClick={() => {
                    setCollapsedArray(
                      message.annotations?.codeSuggestions!.map(() => true) ||
                        []
                    )
                    setSuggestedChanges(
                      (suggestedChanges: StatefulCodeSuggestion[]) => [
                        ...suggestedChanges,
                        ...message.annotations?.codeSuggestions!,
                      ]
                    )
                  }}
                >
                  <FaPlus />
                  &nbsp;Stage All Changes
                </Button>
              )}
            </div>
            {message.annotations?.codeSuggestions?.map(
              (suggestion: StatefulCodeSuggestion, index: number) => {
                const fileExtension = suggestion.filePath.split('.').pop()
                let languageExtension = languageMapping['js']
                if (fileExtension) {
                  languageExtension = languageMapping[fileExtension]
                }
                let diffLines = Diff.diffLines(
                  suggestion.originalCode.trim(),
                  suggestion.newCode.trim()
                )
                let numLinesAdded = 0
                let numLinesRemoved = 0
                for (const line of diffLines) {
                  if (line.added) {
                    numLinesAdded += line.count
                  } else if (line.removed) {
                    numLinesRemoved += line.count
                  }
                }
                const firstLines = truncate(
                  suggestion.originalCode.split('\n').slice(0, 1).join('\n') ||
                    suggestion.newCode.split('\n').slice(0, 1).join('\n'),
                  80
                )
                return (
                  <div
                    className="flex flex-col border border-zinc-800"
                    key={index}
                  >
                    <div className="flex justify-between items-center bg-zinc-800 rounded-t-md p-2">
                      <div className="flex items-center">
                        <Button
                          variant="secondary"
                          size="sm"
                          className="mr-2"
                          onClick={() =>
                            setCollapsedArray((collapsedArray: boolean[]) => {
                              const newArray = [...collapsedArray]
                              newArray[index] = !newArray[index]
                              return newArray
                            })
                          }
                        >
                          {collapsedArray[index] ? (
                            <FaChevronDown />
                          ) : (
                            <FaChevronUp />
                          )}
                        </Button>
                        <code className="text-zinc-200 px-2">
                          {suggestion.filePath}{' '}
                          {numLinesAdded > 0 && (
                            <span className="text-green-500 mr-2">
                              +{numLinesAdded}
                            </span>
                          )}
                          {numLinesRemoved > 0 && (
                            <span className="text-red-500 mr-2">
                              -{numLinesRemoved}
                            </span>
                          )}
                          <span className="text-zinc-500 ml-4">
                            {firstLines}
                          </span>
                        </code>
                      </div>
                      <div className="flex items-center">
                        {suggestion.error ? (
                          <HoverCard openDelay={300} closeDelay={200}>
                            <HoverCardTrigger>
                              <FaExclamationTriangle
                                className="hover:cursor-pointer mr-4 text-yellow-500"
                                style={{ marginTop: 2 }}
                              />
                            </HoverCardTrigger>
                            <HoverCardContent className="w-[800px] max-h-[500px] overflow-y-auto">
                              <MarkdownRenderer
                                content={`**This patch could not be directly applied. We will send the LLM the following message to resolve the error:**\n\n${suggestion.error}`}
                              />
                            </HoverCardContent>
                          </HoverCard>
                        ) : (
                          <HoverCard openDelay={300} closeDelay={200}>
                            <HoverCardTrigger>
                              <FaCheck className="text-green-500 mr-4" />
                            </HoverCardTrigger>
                            <HoverCardContent className="w-[800px] max-h-[500px] overflow-y-auto">
                              <p>
                                No errors found. This patch can be applied
                                directly into the codebase.
                              </p>
                            </HoverCardContent>
                          </HoverCard>
                        )}
                        <Button
                          className="bg-green-800 hover:bg-green-700 text-white"
                          size="sm"
                          onClick={() => {
                            setSuggestedChanges(
                              (suggestedChanges: StatefulCodeSuggestion[]) => [
                                ...suggestedChanges,
                                suggestion,
                              ]
                            )
                            setCollapsedArray((collapsedArray: boolean[]) => {
                              const newArray = [...collapsedArray]
                              newArray[index] = true
                              return newArray
                            })
                          }}
                        >
                          <FaPlus />
                          &nbsp;Stage Change
                        </Button>
                      </div>
                    </div>
                    {!collapsedArray[index] && codeMirrors[index]}
                  </div>
                )
              }
            )}
          </div>
        )}
    </>
  )
}