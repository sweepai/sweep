'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Input } from '../components/ui/input'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import {
  FaArrowLeft,
  FaCheck,
  FaChevronDown,
  FaChevronUp,
  FaCog,
  FaComments,
  FaExclamationTriangle,
  FaGithub,
  FaPaperPlane,
  FaPencilAlt,
  FaPlus,
  FaShareAlt,
  FaSignOutAlt,
  FaStop,
  FaThumbsDown,
  FaThumbsUp,
  FaTimes,
  FaTrash,
  FaCodeBranch,
} from 'react-icons/fa'
import { FaArrowsRotate } from 'react-icons/fa6'
import { Button } from '@/components/ui/button'
import { useLocalStorage } from 'usehooks-ts'
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuIndicator,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
  NavigationMenuViewport,
} from '@/components/ui/navigation-menu'
import { AutoComplete } from '@/components/ui/autocomplete'
import { Toaster } from '@/components/ui/toaster'
import { toast } from '@/components/ui/use-toast'
import { useSession, signIn, SessionProvider, signOut } from 'next-auth/react'
import { Session } from 'next-auth'
import { PostHogProvider, usePostHog } from 'posthog-js/react'
import Survey from './Survey'
import * as jsonpatch from 'fast-json-patch'
import { Textarea } from './ui/textarea'
import { Slider } from './ui/slider'
import { Dialog, DialogContent, DialogTrigger } from './ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu'
import { Label } from './ui/label'
import PulsingLoader from './shared/PulsingLoader'
import {
  codeStyle,
  DEFAULT_K,
  modelMap,
  roleToColor,
  typeNameToColor,
  languageMapping,
} from '@/lib/constants'
import {
  Repository,
  Snippet,
  FileDiff,
  PullRequest,
  Message,
  CodeSuggestion,
  StatefulCodeSuggestion,
  ChatSummary,
} from '@/lib/types'

import { Octokit } from 'octokit'
import {
  renderPRDiffs,
  getJSONPrefix,
  getFunctionCallHeaderString,
  getDiff,
} from '@/lib/str_utils'
import {
  CODE_CHANGE_PATTERN,
  MarkdownRenderer,
} from './shared/MarkdownRenderer'
import { SnippetBadge } from './shared/SnippetBadge'
import { ContextSideBar } from './shared/ContextSideBar'
import { posthog } from '@/lib/posthog'

import CodeMirrorMerge from 'react-codemirror-merge'
import { dracula } from '@uiw/codemirror-theme-dracula'
import { EditorView } from 'codemirror'
import { debounce } from 'lodash'
import { formatDistanceToNow } from 'date-fns';
import { streamMessages } from '@/lib/streamingUtils'
import { Alert, AlertDescription, AlertTitle } from './ui/alert'
import { Skeleton } from './ui/skeleton'
import { isPullRequestEqual } from '@/lib/pullUtils'
// @ts-ignore
import * as Diff from 'diff'

const Original = CodeMirrorMerge.Original
const Modified = CodeMirrorMerge.Modified

const sum = (arr: number[]) => arr.reduce((acc, cur) => acc + cur, 0)
const truncate = (str: string, maxLength: number) =>
  str.length > maxLength ? str.slice(0, maxLength) + '...' : str

const PullRequestHeader = ({ pr }: { pr: PullRequest }) => {
  return (
    <div
      className="bg-zinc-800 rounded-xl p-4 mb-2 text-left hover:bg-zinc-700 hover:cursor-pointer max-w-[800px]"
      onClick={() => {
        window.open(
          `https://github.com/${pr.repo_name}/pull/${pr.number}`,
          '_blank'
        )
      }}
    >
      <div
        className={`border-l-4 ${
          pr.status === 'open'
            ? 'border-green-500'
            : pr.status === 'merged'
              ? 'border-purple-500'
              : 'border-red-500'
        } pl-4`}
      >
        <div className="mb-2 font-bold text-md">
          #{pr.number} {pr.title}
        </div>
        <div className="mb-4 text-sm">{pr.body}</div>
        <div className="text-xs text-zinc-300">
          <div className="mb-1">{pr.repo_name}</div>
          {pr.file_diffs.length} files changed{' '}
          <span className="text-green-500">
            +{sum(pr.file_diffs.map((diff) => diff.additions))}
          </span>{' '}
          <span className="text-red-500">
            -{sum(pr.file_diffs.map((diff) => diff.deletions))}
          </span>
        </div>
      </div>
    </div>
  )
}

const PullRequestContent = ({ pr }: { pr: PullRequest }) => {
  return (
    <>
      <div className="p-4">
        <h2 className="text-sm font-semibold mb-2">Files changed</h2>
        <div className="text-sm text-gray-300">
          <ol>
            {pr.file_diffs.map((file, index) => (
              <li key={index} className="mb-1">
                {file.filename}{' '}
                <span
                  className={`${
                    file.status === 'added'
                      ? 'text-green-500'
                      : file.status === 'removed'
                        ? 'text-red-500'
                        : 'text-gray-400'
                  }`}
                >
                  {file.status === 'added' ? (
                    <span className="text-green-500">
                      Added (+{file.additions})
                    </span>
                  ) : file.status === 'removed' ? (
                    <span className="text-red-500">
                      Deleted ({file.deletions})
                    </span>
                  ) : (
                    <>
                      <span className="text-green-500">+{file.additions}</span>{' '}
                      <span className="text-red-500">-{file.deletions}</span>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <SyntaxHighlighter
        language="diff"
        style={codeStyle}
        customStyle={{
          backgroundColor: 'transparent',
          whiteSpace: 'pre-wrap',
        }}
        className="rounded-xl p-4 text-xs w-full"
      >
        {renderPRDiffs(pr)}
      </SyntaxHighlighter>
    </>
  )
}

const PullRequestDisplay = ({
  pr,
  useHoverCard = true,
}: {
  pr: PullRequest
  useHoverCard?: boolean
}) => {
  if (useHoverCard) {
    return (
      <HoverCard openDelay={300} closeDelay={200}>
        <HoverCardTrigger>
          <PullRequestHeader pr={pr} />
        </HoverCardTrigger>
        <HoverCardContent className="w-[800px] max-h-[600px] overflow-y-auto">
          <PullRequestContent pr={pr} />
        </HoverCardContent>
      </HoverCard>
    )
  } else {
    return (
      <div className="flex justify-end flex-col">
        <PullRequestHeader pr={pr} />
        <div className="bg-zinc-800 rounded-xl p-4 mb-2 text-left max-w-[800px]">
          <PullRequestContent pr={pr} />
        </div>
      </div>
    )
  }
}

const UserMessageDisplay = ({
  message,
  onEdit,
}: {
  message: Message
  onEdit: (content: string) => void
}) => {
  // TODO: finish this implementation
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
  }, [editedContent])

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
                className="w-full mb-4 bg-transparent text-white max-w-[500px] w-[500px] hover:bg-initial"
                ref={textareaRef}
                value={editedContent}
                onChange={(e) => setEditedContent(e.target.value)}
                autoFocus
              />
            ) : (
              <MarkdownRenderer content={message.content.trim()} />
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
                className="ml-2 bg-slate-600 text-white hover:bg-slate-700"
              >
                Generate
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

const FeedbackBlock = ({
  message,
  index,
}: {
  message: Message
  index: number
}) => {
  const [isLiked, setIsLiked] = useState(false)
  const [isDisliked, setIsDisliked] = useState(false)
  return (
    <div className="flex justify-end my-2">
      <FaThumbsUp
        className={`inline-block text-lg ${
          isLiked
            ? 'text-green-500 cursor-not-allowed'
            : 'text-zinc-400 hover:cursor-pointer hover:text-zinc-200 hover:drop-shadow-md'
        }`}
        onClick={() => {
          if (isLiked) {
            return
          }
          posthog.capture('message liked', {
            message: message,
            index: index,
          })
          toast({
            title: 'We received your like',
            description:
              'Thank you for your feedback! If you would like to share any highlights, feel free to shoot us a message on Slack!',
            variant: 'default',
            duration: 2000,
          })
          setIsLiked(true)
          setIsDisliked(false)
        }}
      />
      <FaThumbsDown
        className={`inline-block ml-3 text-lg ${
          isDisliked
            ? 'text-red-500 cursor-not-allowed'
            : 'text-zinc-400 hover:cursor-pointer hover:text-zinc-200 hover:drop-shadow-md'
        }`}
        onClick={() => {
          if (isDisliked) {
            return
          }
          posthog.capture('message disliked', {
            message: message,
            index: index,
          })
          toast({
            title: 'We received your dislike',
            description:
              'Thank you for your feedback! If you would like to report any persistent issues, feel free to shoot us a message on Slack!',
            variant: 'default',
            duration: 2000,
          })
          setIsDisliked(true)
          setIsLiked(false)
        }}
      />
    </div>
  )
}

const MessageDisplay = ({
  message,
  className,
  onEdit,
  repoName,
  branch,
  commitToPR,
  setSuggestedChanges,
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
  index: number
}) => {
  const [collapsedArray, setCollapsedArray] = useState<boolean[]>(
    message.annotations?.codeSuggestions?.map(() => false) || []
  )
  const codeMirrors = useMemo(() => {
    return (
      message.annotations?.codeSuggestions?.map((suggestion) => {
        const fileExtension = suggestion.filePath.split('.').pop()
        let languageExtension = languageMapping['js']
        if (fileExtension) {
          languageExtension = languageMapping[fileExtension]
        }
        return (
          <CodeMirrorMerge
            hidden={collapsedArray[index]}
            className="w-full"
            theme={dracula}
            collapseUnchanged={{
              margin: 3,
              minSize: 4,
            }}
            autoFocus={false}
            key={JSON.stringify(suggestion)}
          >
            <Original
              value={suggestion.originalCode}
              readOnly={true}
              extensions={[
                EditorView.editable.of(false),
                ...(languageExtension ? [languageExtension] : []),
              ]}
            />
            <Modified
              value={suggestion.newCode}
              readOnly={true}
              extensions={[
                EditorView.editable.of(false),
                ...(languageExtension ? [languageExtension] : []),
              ]}
            />
          </CodeMirrorMerge>
        )
      }) || []
    )
  }, [message.annotations?.codeSuggestions])
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
                        className="reactMarkdown mt-4 mb-0 py-2"
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
          <PullRequestDisplay pr={pr} />
        </div>
      ))}
      {message.annotations?.codeSuggestions &&
        message.annotations?.codeSuggestions.length > 0 && (
          <div className="text-sm max-w-[80%] p-4 rounded bg-zinc-700 space-y-4 mb-4">
            <Button
              className="bg-green-800 hover:bg-green-700 text-white"
              size="sm"
              onClick={() => {
                setCollapsedArray(
                  message.annotations?.codeSuggestions!.map(() => true) || []
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
                  suggestion.originalCode.split('\n').slice(0, 1).join('\n'),
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
                          <span className="text-green-500">
                            +{numLinesAdded}
                          </span>{' '}
                          <span className="text-red-500">
                            -{numLinesRemoved}
                          </span>{' '}
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
                                className="hover:cursor-pointer mr-4 text-red-500"
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
                    {codeMirrors[index]}
                  </div>
                )
              }
            )}
          </div>
        )}
    </>
  )
}

const parsePullRequests = async (
  repoName: string,
  message: string,
  octokit: Octokit
): Promise<PullRequest[]> => {
  const [orgName, repo] = repoName.split('/')
  const pulls = []

  try {
    const prURLs = message.match(
      new RegExp(
        `https?:\/\/github.com\/${repoName}\/pull\/(?<prNumber>[0-9]+)`,
        'gm'
      )
    )
    for (const prURL of prURLs || []) {
      const prNumber = prURL.split('/').pop()
      const pr = await octokit!.rest.pulls.get({
        owner: orgName,
        repo: repo,
        pull_number: parseInt(prNumber!),
      })
      const title = pr.data.title
      const body = pr.data.body
      const labels = pr.data.labels.map((label) => label.name)
      const status =
        pr.data.state === 'open' ? 'open' : pr.data.merged ? 'merged' : 'closed'
      const file_diffs = (
        await octokit!.rest.pulls.listFiles({
          owner: orgName,
          repo: repo,
          pull_number: parseInt(prNumber!),
        })
      ).data.sort((a, b) => {
        const aIsMarkdown = a.filename.endsWith('.md') || a.filename.endsWith('.rst')
        const bIsMarkdown = b.filename.endsWith('.md') || b.filename.endsWith('.rst')
        if (aIsMarkdown !== bIsMarkdown) {
          return aIsMarkdown ? 1 : -1;
        }
        const statusOrder: Record<string, number> = {
          renamed: 0,
          copied: 1,
          added: 2,
          modified: 3,
          changed: 4,
          deleted: 5,
          unchanged: 6,
        }
        if (statusOrder[a.status] !== statusOrder[b.status]) {
          return statusOrder[a.status] - statusOrder[b.status]
        }
        return b.changes - a.changes
      })
      pulls.push({
        number: parseInt(prNumber!),
        repo_name: repoName,
        title,
        body,
        labels,
        status,
        file_diffs,
        branch: pr.data.head.ref,
      } as PullRequest)
    }

    return pulls
  } catch (e: any) {
    toast({
      title: 'Failed to retrieve pull request',
      description: `The following error has occurred: ${e.message}. Sometimes, logging out and logging back in can resolve this issue.`,
      variant: 'destructive',
    })
    return []
  }
}

function App({ defaultMessageId = '' }: { defaultMessageId?: string }) {
  const [repoName, setRepoName] = useState<string>('')
  const [branch, setBranch] = useState<string>('main')
  const [repoNameValid, setRepoNameValid] = useState<boolean>(false)
  const [repoNameDisabled, setRepoNameDisabled] = useState<boolean>(false)

  const [k, setK] = useLocalStorage<number>('k', DEFAULT_K)
  const [model, setModel] = useLocalStorage<keyof typeof modelMap>(
    'model',
    'gpt-4o'
  )
  const [snippets, setSnippets] = useState<Snippet[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [currentMessage, setCurrentMessage] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const isStream = useRef<boolean>(false)
  const [showSurvey, setShowSurvey] = useState<boolean>(false)

  const [originalSuggestedChanges, setOriginalSuggestedChanges] = useState<
    StatefulCodeSuggestion[]
  >([])
  const [suggestedChanges, setSuggestedChanges] = useState<
    StatefulCodeSuggestion[]
  >([])
  const [codeSuggestionsState, setCodeSuggestionsState] = useState<
    'staging' | 'validating' | 'creating' | 'done'
  >('staging')
  const [isProcessingSuggestedChanges, setIsProcessingSuggestedChanges] =
    useState<boolean>(false)
  const [pullRequestTitle, setPullRequestTitle] = useState<string | null>(null)
  const [pullRequestBody, setPullRequestBody] = useState<string | null>(null)
  const [isCreatingPullRequest, setIsCreatingPullRequest] =
    useState<boolean>(false)
  const [userMentionedPullRequest, setUserMentionedPullRequest] =
    useState<PullRequest | null>(null)
  const [userMentionedPullRequests, setUserMentionedPullRequests] = useState<
    PullRequest[] | null
  >(null)
  const [pullRequest, setPullRequest] = useState<PullRequest | null>(null)
  const [baseBranch, setBaseBranch] = useState<string>(branch)
  const [featureBranch, setFeatureBranch] = useState<string | null>(null)
  const [commitToPR, setCommitToPR] = useState<boolean>(false) // controls whether or not we commit to the userMetionedPullRequest or create a new pr
  const [commitToPRIsOpen, setCommitToPRIsOpen] = useState<boolean>(false)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [commitMessage, setCommitMessage] = useState<string>('')

  const { data: session } = useSession()

  const posthog = usePostHog()
  const [octokit, setOctokit] = useState<Octokit | null>(null)
  const [repos, setRepos] = useState<Repository[]>([])

  const [messagesId, setMessagesId] = useState<string>(defaultMessageId)
  const [previousChats, setPreviousChats] = useLocalStorage<ChatSummary[]>(
    'previousChats',
    []
  )

  const authorizedFetch = useCallback(
    (url: string, options: RequestInit = {}) => {
      return fetch(url, {
        method: 'POST',
        headers: {
          ...options.headers,
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.user.accessToken}`,
        },
        ...options,
      })
    },
    [session?.user.accessToken]
  )

  useEffect(() => {
    if (messagesId && !previousChats.some((chat) => chat.messagesId === messagesId) && messages.length > 0) {
      setPreviousChats([...previousChats, {
        messagesId: messagesId,
        createdAt: new Date().toISOString(),
        initialMessage: messages[0].content
      }])
    }
  }, [messagesId, messages.length])

  useEffect(() => {
    console.log('loading message', messagesId)
    if (messagesId) {
      ;(async () => {
        const response = await authorizedFetch(
          `/backend/messages/load/${messagesId}`,
          {
            method: 'GET',
          }
        )
        const data = await response.json()
        if (data.status == 'success') {
          const {
            repo_name,
            messages,
            snippets,
            original_code_suggestions,
            code_suggestions,
            pull_request,
            pull_request_title,
            pull_request_body,
            user_mentioned_pull_request,
            user_mentioned_pull_requests,
            commit_to_pr,
          } = data.data
          console.log(
            repo_name,
            messages,
            snippets,
            user_mentioned_pull_requests
          )
          setRepoName(repo_name)
          setRepoNameValid(true)
          setMessages(messages)
          setSnippets(snippets)
          setOriginalSuggestedChanges(original_code_suggestions)
          setSuggestedChanges(code_suggestions)
          setPullRequest(pull_request)
          setPullRequestTitle(pull_request_title)
          setPullRequestBody(pull_request_body)
          setUserMentionedPullRequest(user_mentioned_pull_request)
          setUserMentionedPullRequests(user_mentioned_pull_requests)
          if (commit_to_pr === 'true') {
            setCommitToPR(true)
          } else {
            setCommitToPR(false)
          }
        } else {
          toast({
            title: 'Failed to load message',
            description: `The following error has occurred: ${data.error}. Sometimes, logging out and logging back in can resolve this issue.`,
            variant: 'destructive',
          })
        }
      })()
    }
  }, [messagesId])

  useEffect(() => {
    if (messagesContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } =
        messagesContainerRef.current
      if (scrollHeight - scrollTop - clientHeight < 80) {
        messagesContainerRef.current.scrollTop =
          messagesContainerRef.current.scrollHeight
      }
    }
  }, [messages])

  useEffect(() => {
    if (session) {
      const octokit = new Octokit({ auth: session.user!.accessToken })
      setOctokit(octokit)
      ;(async () => {
        const maxPages = 5
        let allRepositories: Repository[] = []
        let page = 1
        let response
        do {
          response = await octokit.rest.repos.listForAuthenticatedUser({
            visibility: 'all',
            sort: 'pushed',
            per_page: 100,
            page: page,
          })
          allRepositories = allRepositories.concat(response.data)
          setRepos(allRepositories)
          page++
        } while (response.data.length !== 0 && page < maxPages)
      })()
    }
  }, [session?.user!.accessToken])

  useEffect(() => {
    if (branch) {
      setBaseBranch(branch)
    }
    if (messages.length > 0) {
      for (const message of messages) {
        if (
          message.annotations?.pulls &&
          message.annotations.pulls.length > 0 &&
          message.annotations.pulls[0].branch
        ) {
          setBaseBranch(message.annotations.pulls[0].branch)
        }
      }
    }
  }, [branch, messages])

  useEffect(() => {
    if (repoName && octokit) {
      ;(async () => {
        const repoData = await octokit.rest.repos.get({
          owner: repoName.split('/')[0],
          repo: repoName.split('/')[1],
        })
        setBranch(repoData.data.default_branch)
        setBaseBranch(repoData.data.default_branch)
      })()
    }
  }, [repoName])

  useEffect(() => {
    if (suggestedChanges.length == 0) {
      setCodeSuggestionsState('staging')
    }
  }, [suggestedChanges])

  const save = async (
    currentRepoName: string,
    currentMessages: Message[],
    currentSnippets: Snippet[],
    currentMessagesId: string,
    currentUserMentionedPullRequest: PullRequest | null = null,
    currentUserMentionedPullRequests: PullRequest[] | null = null,
    currentCommitToPR: boolean = false,
    currentOriginalCodeSuggestions: StatefulCodeSuggestion[],
    currentSuggestedChanges: StatefulCodeSuggestion[],
    currentPullRequest: PullRequest | null = null,
    currentPullRequestTitle: string | null = null,
    currentPullRequestBody: string | null = null
  ) => {
    const commitToPRString: string =
      currentCommitToPR || commitToPR ? 'true' : 'false'
    const saveResponse = await fetch('/backend/messages/save', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // @ts-ignore
        Authorization: `Bearer ${session?.user.accessToken}`,
      },
      body: JSON.stringify({
        repo_name: currentRepoName || repoName,
        messages: currentMessages || messages,
        snippets: currentSnippets || snippets,
        message_id: currentMessagesId || '',
        original_code_suggestions:
          currentOriginalCodeSuggestions || originalSuggestedChanges,
        code_suggestions: currentSuggestedChanges || originalSuggestedChanges,
        pull_request: currentPullRequest || pullRequest,
        pull_request_title: currentPullRequestTitle || pullRequestTitle,
        pull_request_body: currentPullRequestBody || pullRequestBody,
        user_mentioned_pull_request:
          currentUserMentionedPullRequest || userMentionedPullRequest,
        user_mentioned_pull_requests:
          currentUserMentionedPullRequests || userMentionedPullRequests,
        commit_to_pr: commitToPRString,
      }),
    })
    const saveData = await saveResponse.json()
    if (saveData.status == 'success') {
      const { message_id } = saveData
      if (!currentMessagesId && message_id) {
        setMessagesId(message_id)
        const updatedUrl = `/c/${message_id}`
        window.history.pushState({}, '', updatedUrl)
      }
    } else {
      console.warn('Failed to save message', saveData)
    }
  }

  const debouncedSave = useCallback(
    debounce(
      (
        repoName,
        messages,
        snippets,
        currentMessagesId,
        userMentionedPullRequest,
        userMentionedPullRequests,
        commitToPR,
        originalSuggestedChanges,
        suggestedChanges,
        pullRequest,
        pullRequestTitle,
        pullRequestBody
      ) => {
        console.log('saving...')
        save(
          repoName,
          messages,
          snippets,
          currentMessagesId,
          userMentionedPullRequest,
          userMentionedPullRequests,
          commitToPR,
          originalSuggestedChanges,
          suggestedChanges,
          pullRequest,
          pullRequestTitle,
          pullRequestBody
        )
      },
      2000,
      { leading: true, maxWait: 5000 }
    ),
    []
  ) // can tune these timeouts

  useEffect(() => {
    if (messages.length > 0 && snippets.length > 0) {
      debouncedSave(
        repoName,
        messages,
        snippets,
        messagesId,
        userMentionedPullRequest,
        userMentionedPullRequests,
        commitToPR,
        originalSuggestedChanges,
        suggestedChanges,
        pullRequest,
        pullRequestTitle,
        pullRequestBody
      )
    }
  }, [
    repoName,
    messages,
    snippets,
    messagesId,
    userMentionedPullRequest,
    userMentionedPullRequests,
    commitToPR,
    originalSuggestedChanges,
    suggestedChanges,
    pullRequest,
    pullRequestTitle,
    pullRequestBody,
  ])

  const reactCodeMirrors = suggestedChanges.map((suggestion, index) => {
    const fileExtension = suggestion.filePath.split('.').pop()
    // default to javascript
    let languageExtension = languageMapping['js']
    if (fileExtension) {
      languageExtension = languageMapping[fileExtension]
    }

    return (
      <CodeMirrorMerge
        theme={dracula}
        revertControls={'a-to-b'}
        collapseUnchanged={{
          margin: 3,
          minSize: 4,
        }}
        autoFocus={false}
        key={JSON.stringify(suggestion)}
      >
        <Original
          value={suggestion.originalCode}
          readOnly={true}
          extensions={[
            EditorView.editable.of(false),
            ...(languageExtension ? [languageExtension] : []),
          ]}
        />
        <Modified
          value={suggestion.newCode}
          readOnly={
            !(suggestion.state == 'done' || suggestion.state == 'error')
          }
          extensions={[
            EditorView.editable.of(
              suggestion.state == 'done' || suggestion.state == 'error'
            ),
            ...(languageExtension ? [languageExtension] : []),
          ]}
          onChange={debounce((value: string) => {
            setSuggestedChanges((suggestedChanges) =>
              suggestedChanges.map((suggestion, i) =>
                i == index ? { ...suggestion, newCode: value } : suggestion
              )
            )
          }, 1000)}
        />
      </CodeMirrorMerge>
    )
  })

  if (session) {
    posthog.identify(session.user!.email!, {
      email: session.user!.email,
      name: session.user!.name,
      image: session.user!.image,
    })
  } else {
    return (
      <main className="flex h-screen items-center justify-center p-12">
        <Toaster />
        <Button onClick={() => signIn('github')} variant="secondary">
          <FaGithub className="inline-block mr-2" style={{ marginTop: -2 }} />
          Sign in with GitHub
        </Button>
      </main>
    )
  }

  const lastAssistantMessageIndex = messages.findLastIndex(
    (message) =>
      message.role === 'assistant' &&
      !message.annotations?.pulls &&
      message.content.trim().length > 0
  )

  const applySuggestions = async (
    codeSuggestions: CodeSuggestion[],
    commitToPR: boolean
  ) => {
    isStream.current = true
    let currentCodeSuggestions: StatefulCodeSuggestion[] = codeSuggestions.map(
      (suggestion) => ({
        ...suggestion,
        state: 'pending',
      })
    )
    setSuggestedChanges(currentCodeSuggestions)
    setIsProcessingSuggestedChanges(true)
    ;(async () => {
      const streamedResponse = await authorizedFetch(`/backend/autofix`, {
        body: JSON.stringify({
          repo_name: repoName,
          code_suggestions: codeSuggestions.map(
            (suggestion: CodeSuggestion) => ({
              file_path: suggestion.filePath,
              original_code: suggestion.originalCode,
              new_code: suggestion.newCode,
            })
          ),
          branch: baseBranch,
        }), // TODO: casing should be automatically handled
      })

      try {
        const reader = streamedResponse.body!.getReader()
        for await (const currentState of streamMessages(
          reader,
          isStream,
          5 * 60 * 1000
        )) {
          // console.log(currentState)
          if (currentState.error) {
            throw new Error(currentState.error)
          }
          currentCodeSuggestions = currentState.map((suggestion: any) => ({
            filePath: suggestion.file_path,
            originalCode: suggestion.original_code,
            newCode: suggestion.new_code,
            fileContents: suggestion.file_contents,
            state: suggestion.state,
            error: suggestion.error,
          }))
          setSuggestedChanges(currentCodeSuggestions)
        }
        if (!isStream.current) {
          currentCodeSuggestions = currentCodeSuggestions.map((suggestion) =>
            suggestion.state == 'done'
              ? suggestion
              : {
                  ...suggestion,
                  originalCode:
                    suggestion.fileContents || suggestion.originalCode,
                  state: 'error',
                }
          )
          setSuggestedChanges(currentCodeSuggestions)
        }
      } catch (e: any) {
        console.error(e)
        toast({
          title: 'Failed to auto-fix changes!',
          description:
            'The following error occurred while applying these changes:\n\n' +
            e.message +
            '\n\nFeel free to shoot us a message if you keep running into this!',
          variant: 'destructive',
          duration: Infinity,
        })
        currentCodeSuggestions = currentCodeSuggestions.map((suggestion) =>
          suggestion.state == 'done'
            ? suggestion
            : {
                ...suggestion,
                originalCode:
                  suggestion.fileContents || suggestion.originalCode,
                state: 'error',
              }
        )
        console.log(currentCodeSuggestions)
        setSuggestedChanges(currentCodeSuggestions)
        posthog.capture('auto fix error', {
          error: e.message,
        })
      } finally {
        isStream.current = false
        setIsProcessingSuggestedChanges(false)

        if (!featureBranch || !pullRequestTitle || !pullRequestBody) {
          const prMetadata = await authorizedFetch(
            '/backend/create_pull_metadata',
            {
              body: JSON.stringify({
                repo_name: repoName,
                modify_files_dict: suggestedChanges.reduce(
                  (
                    acc: Record<
                      string,
                      { original_contents: string; contents: string }
                    >,
                    suggestion: StatefulCodeSuggestion
                  ) => {
                    acc[suggestion.filePath] = {
                      original_contents: suggestion.originalCode,
                      contents: suggestion.newCode,
                    }
                    return acc
                  },
                  {}
                ),
                messages: messages,
              }),
            }
          )

          const prData = await prMetadata.json()
          const { title, description, branch: featureBranch } = prData
          setFeatureBranch(
            featureBranch ||
              'sweep-chat-suggested-changes-' +
                new Date()
                  .toISOString()
                  .slice(0, 19)
                  .replace('T', '_')
                  .replace(':', '_')
          )
          setPullRequestTitle(title || 'Sweep Chat Suggested Changes')
          setPullRequestBody(description || 'Suggested changes by Sweep Chat.')
        }
      }
    })()
  }

  const startStream = async (
    message: string,
    newMessages: Message[],
    snippets: Snippet[],
    annotations: { pulls: PullRequest[] } = { pulls: [] }
  ) => {
    setIsLoading(true)
    isStream.current = true
    var currentSnippets = snippets
    if (currentSnippets.length == 0) {
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
            query: message,
            annotations: annotations,
            branch: baseBranch,
          }),
        })

        let streamedMessages: Message[] = [...newMessages]
        let streamedMessage: string = ''
        const reader = snippetsResponse.body?.getReader()!
        for await (const chunk of streamMessages(reader, isStream)) {
          streamedMessage = chunk[0]
          currentSnippets = chunk[1]
          currentSnippets = currentSnippets.slice(0, k)
          streamedMessages = [
            ...newMessages,
            {
              content: streamedMessage,
              role: 'function',
              function_call: {
                function_name: 'search_codebase',
                function_parameters: {},
                snippets: currentSnippets,
                is_complete: false,
              },
            } as Message,
          ]
          if (currentSnippets) {
            setSnippets(currentSnippets)
          }
          setMessages(streamedMessages)
        }
        streamedMessages = [
          ...streamedMessages.slice(0, streamedMessages.length - 1),
          {
            ...streamedMessages[streamedMessages.length - 1],
            function_call: {
              function_name: 'search_codebase',
              function_parameters: {},
              snippets: currentSnippets,
              is_complete: true,
            },
          },
        ]
        setMessages(streamedMessages)
        if (!currentSnippets.length) {
          throw new Error('No snippets found')
        }
      } catch (e: any) {
        console.log(e)
        toast({
          title: 'Failed to search codebase',
          description: `The following error has occurred: ${e.message}. Sometimes, logging out and logging back in can resolve this issue.`,
          variant: 'destructive',
          duration: Infinity,
        })
        setIsLoading(false)
        isStream.current = false
        posthog.capture('chat errored', {
          repoName,
          snippets,
          newMessages,
          message,
          error: e.message,
        })
        throw e
      }
    }

    const chatResponse = await fetch('/backend/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // @ts-ignore
        Authorization: `Bearer ${session?.user.accessToken}`,
      },
      body: JSON.stringify({
        repo_name: repoName,
        messages: newMessages,
        snippets: currentSnippets,
        model: model,
        branch: baseBranch,
        k: k,
      }),
    })

    // Stream
    const reader = chatResponse.body?.getReader()!
    var streamedMessages: Message[] = []
    var respondedMessages: Message[] = [
      ...newMessages,
      { content: '', role: 'assistant' } as Message,
    ]
    setMessages(respondedMessages)
    let messageLength = newMessages.length
    try {
      for await (const patch of streamMessages(reader, isStream)) {
        streamedMessages = jsonpatch.applyPatch(
          streamedMessages,
          patch
        ).newDocument
        setMessages([...newMessages, ...streamedMessages])
        if (streamedMessages.length > messageLength) {
          messageLength = streamedMessages.length
        }
      }
      if (!isStream.current) {
        reader!.cancel()
        posthog.capture('chat stopped', {
          repoName,
          snippets,
          newMessages,
          message,
        })
      }
    } catch (e: any) {
      toast({
        title: 'Chat stream failed',
        description: e.message,
        variant: 'destructive',
        duration: Infinity,
      })
      setIsLoading(false)
      posthog.capture('chat errored', {
        repoName,
        snippets,
        newMessages,
        message,
        error: e.message,
      })
      throw e
    }

    isStream.current = false

    var lastMessage = streamedMessages[streamedMessages.length - 1]
    if (
      lastMessage.role == 'function' &&
      lastMessage.function_call?.is_complete == false
    ) {
      lastMessage.function_call.is_complete = true
      setMessages([
        ...newMessages,
        ...streamedMessages.slice(0, streamedMessages.length - 1),
        lastMessage,
      ])
    }

    const surveyID = process.env.NEXT_PUBLIC_SURVEY_ID
    if (
      surveyID &&
      !localStorage.getItem(`hasInteractedWithSurvey_${surveyID}`)
    ) {
      setShowSurvey(true)
    }
    setIsLoading(false)
    posthog.capture('chat succeeded', {
      repoName,
      snippets,
      newMessages,
      message,
    })
  }

  const sendMessage = async () => {
    posthog.capture('chat submitted', {
      repoName,
      snippets,
      messages,
      currentMessage,
    })
    let newMessages: Message[] = [
      ...messages,
      { content: currentMessage, role: 'user' },
    ]
    setMessages(newMessages)
    setCurrentMessage('')
    const pulls = await parsePullRequests(repoName, currentMessage, octokit!)
    if (pulls.length) {
      setUserMentionedPullRequest(pulls[pulls.length - 1])
      setCommitToPR(true)
    }
    let newPulls = userMentionedPullRequests
      ? [...userMentionedPullRequests]
      : []

    pulls.forEach((pull1) => {
      if (!newPulls.some((pull2) => isPullRequestEqual(pull1, pull2))) {
        newPulls.push(pull1)
      }
    })

    setUserMentionedPullRequests(newPulls)
    newMessages = [
      ...messages,
      { content: currentMessage, role: 'user', annotations: { pulls } },
    ]
    setMessages(newMessages)
    setCurrentMessage('')
    startStream(currentMessage, newMessages, snippets, { pulls })
  }

  return (
    <>
      <main className="flex h-screen flex-col items-center justify-between p-12 pt-20">
        <NavigationMenu className="fixed top-0 left-0 w-[100vw]">
          <div className="flex items-center justify-between w-[100vw] p-4 px-4 mb-2 align-center">
            <img
              src="/banner.png"
              className="h-10 rounded-lg hover:cursor-pointer box-shadow-md"
              onClick={() => {
                window.location.href = '/'
              }}
            />

            <DropdownMenu>
              <DropdownMenuTrigger className="outline-none">
                <p className="text-sm font-bold flex items-center">
                  Previous Chats <FaChevronDown className="ml-2" />
                </p>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="center" className="mt-2">
                {previousChats.length > 0 ? previousChats.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()).slice(0, 10).map((chat) => (
                  <DropdownMenuItem
                    key={chat.messagesId}
                    className="hover:cursor-pointer"
                    onClick={() => {
                      setMessagesId(chat.messagesId)
                      window.location.href = `/c/${chat.messagesId}`
                    }}
                    disabled={chat.messagesId === messagesId}
                  >
                    <b>{truncate(chat.initialMessage, 80)}</b>&nbsp;created {formatDistanceToNow(new Date(chat.createdAt), { addSuffix: true })}
                  </DropdownMenuItem>
                )) : (
                    <DropdownMenuItem>No history</DropdownMenuItem>
                )}
              </DropdownMenuContent>
              {/* Warning: these message IDs are stored in local storage.
                If you want to delete them, you will need to clear your browser cache. */}
            </DropdownMenu>

            <NavigationMenuList className='w-full flex justify-between'>
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="outline" className="ml-4">
                    <FaCog className="mr-2" />
                    Settings
                  </Button>
                </DialogTrigger>
                <DialogContent className="w-120 p-16">
                  <h2 className="text-2xl font-bold mb-4 text-center">Settings</h2>
                  <Label>Model</Label>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" className="text-left">
                        {modelMap[model]}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="w-56">
                      <DropdownMenuLabel>Anthropic</DropdownMenuLabel>
                      <DropdownMenuSeparator />
                      <DropdownMenuRadioGroup
                        value={model}
                        onValueChange={(value) =>
                          setModel(value as keyof typeof modelMap)
                        }
                      >
                        {Object.keys(modelMap).map((model) =>
                          model.includes('claude') ? (
                            <DropdownMenuRadioItem value={model} key={model}>
                              {modelMap[model]}
                            </DropdownMenuRadioItem>
                          ) : null
                        )}
                      </DropdownMenuRadioGroup>
                      <DropdownMenuLabel>OpenAI</DropdownMenuLabel>
                      <DropdownMenuSeparator />
                      <DropdownMenuRadioGroup
                        value={model}
                        onValueChange={(value) =>
                          setModel(value as keyof typeof modelMap)
                        }
                      >
                        {Object.keys(modelMap).map((model) =>
                          model.includes('gpt') ? (
                            <DropdownMenuRadioItem value={model} key={model}>
                              {modelMap[model]}
                            </DropdownMenuRadioItem>
                          ) : null
                        )}
                      </DropdownMenuRadioGroup>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  <Label className="mt-4">Number of snippets</Label>
                  <div className="flex items-center">
                    <span className="mr-4 whitespace-nowrap">{k}</span>
                    <Slider
                      defaultValue={[DEFAULT_K]}
                      max={20}
                      min={1}
                      step={1}
                      onValueChange={(value) => setK(value[0])}
                      value={[k]}
                      className="w-[300px] my-0 py-0"
                    />
                  </div>
                </DialogContent>
              </Dialog>

              <DropdownMenu>
                <DropdownMenuTrigger className="outline-none">
                  <div className="flex items-center w-12 h-12 ml-2">
                    <img
                      className="rounded-full w-10 h-10 m-0"
                      src={session!.user!.image || ''}
                      alt={session!.user!.name || ''}
                    />
                  </div>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>
                    <p className="text-md font-bold">
                      {session!.user!.username! || session!.user!.name}
                    </p>
                  </DropdownMenuLabel>
                  {session?.user?.email && (
                    <DropdownMenuItem>{session.user.email}</DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="cursor-pointer"
                    onClick={() => setShowSurvey((prev) => !prev)}
                  >
                    <FaComments className="mr-2" />
                    Feedback
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="cursor-pointer"
                    onClick={() => signOut()}
                  >
                    <FaSignOutAlt className="mr-2" />
                    Sign Out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </NavigationMenuList>
          </div>
        </NavigationMenu>
        <Toaster />
        {showSurvey && process.env.NEXT_PUBLIC_SURVEY_ID && (
          <Survey
            onClose={(didSubmit) => {
              setShowSurvey(false)
              if (didSubmit) {
                toast({
                  title: 'Thanks for your feedback!',
                  description: "We'll reach back out shortly.",
                })
              }
            }}
          />
        )}
        <div
          className={`mb-4 w-full flex items-center ${
            repoNameValid || messagesId ? '' : 'grow'
          }`}
        >
          <AutoComplete
            options={repos.map((repo) => ({
              label: repo.full_name,
              value: repo.full_name,
            }))}
            placeholder="Repository name"
            emptyMessage="No repositories found"
            value={{ label: repoName, value: repoName }}
            onValueChange={(option) => setRepoName(option.value)}
            disabled={repoNameDisabled}
            onBlur={async (repoName: string) => {
              console.log(repoName)
              const cleanedRepoName = repoName.replace(/\s/g, '') // might be unsafe but we'll handle it once we get there
              console.log(repoName)
              setRepoName(cleanedRepoName)
              if (cleanedRepoName === '') {
                setRepoNameValid(false)
                return
              }
              if (!cleanedRepoName.includes('/')) {
                setRepoNameValid(false)
                toast({
                  title: 'Invalid repository name',
                  description:
                    "Please enter a valid repository name in the format 'owner/repo'",
                  variant: 'destructive',
                  duration: Infinity,
                })
                return
              }
              var data = null
              try {
                setRepoNameDisabled(true)
                const response = await authorizedFetch(
                  `/backend/repo?repo_name=${cleanedRepoName}`,
                  {
                    method: 'GET',
                  }
                )
                data = await response.json()
              } catch (e: any) {
                setRepoNameValid(false)
                toast({
                  title: 'Failed to load repository',
                  description: e.message,
                  variant: 'destructive',
                  duration: Infinity,
                })
                setRepoNameDisabled(false)
                return
              }
              if (!data.success) {
                setRepoNameValid(false)
                toast({
                  title: 'Failed to load repository',
                  description: data.error,
                  variant: 'destructive',
                  duration: Infinity,
                })
              } else {
                setRepoNameValid(true)
                toast({
                  title: 'Successfully loaded repository',
                  variant: 'default',
                })
              }
              setRepoNameDisabled(false)
              if (octokit) {
                const repo = await octokit.rest.repos.get({
                  owner: cleanedRepoName.split('/')[0],
                  repo: cleanedRepoName.split('/')[1],
                })
                setBranch(repo.data.default_branch)
                setBaseBranch(repo.data.default_branch)
              }
            }}
          />
          <Input
            placeholder="Branch"
            className="w-[400px] ml-4"
            value={baseBranch}
            onChange={(e) => setBaseBranch(e.target.value)}
          />
          {repoName ? (
            <NavigationMenu>
              <NavigationMenuList>
                <NavigationMenuItem>
                  <NavigationMenuTrigger className="bg-secondary hover:bg-secondary ml-4" disabled={isLoading || !userMentionedPullRequest}>
                    {userMentionedPullRequest && commitToPR ? (
                      <Button
                        className="w-full"
                        variant="secondary"
                      >
                        <FaCodeBranch />
                        &nbsp;&nbsp;Will commit to PR #
                        {userMentionedPullRequest.number}
                      </Button>
                    ) : (
                      <Button
                        className="w-full"
                        variant="secondary"
                      >
                        <FaCodeBranch />
                        &nbsp;&nbsp;Will create new PR
                      </Button>
                    )}
                  </NavigationMenuTrigger>
                  <NavigationMenuContent>
                    {commitToPR ? (
                      <Button
                        className="w-full"
                        variant="secondary"
                        disabled={isLoading}
                        onClick={() => {
                          setCommitToPR(false)
                          setCommitToPRIsOpen(false)
                        }}
                      >
                        Will create new PR
                      </Button>
                    ) : (
                      <></>
                    )}
                    {// loop through all pull requests
                    userMentionedPullRequests?.map((pr, index) => {
                      // dont show current selected pr, unless we are creating a pr rn
                      if (
                        pr.number !== userMentionedPullRequest?.number ||
                        !commitToPR
                      ) {
                        return (
                          <Button
                            className="w-full"
                            variant="secondary"
                            disabled={isLoading}
                            onClick={() => {
                              setCommitToPR(true)
                              setUserMentionedPullRequest(pr)
                              setCommitToPRIsOpen(false)
                            }}
                            key={index}
                          >
                            <FaCodeBranch />
                            &nbsp;&nbsp;Will commit to {pr.number}
                          </Button>
                        )
                      }
                    })}
                  </NavigationMenuContent>
                </NavigationMenuItem>
              </NavigationMenuList>
            </NavigationMenu>
          ) : (
            <></>
          )}
        </div>
        {snippets.length && repoName ? (
          <ContextSideBar
            snippets={snippets}
            setSnippets={setSnippets}
            repoName={repoName}
            branch={branch}
            k={k}
          />
        ) : (
          <></>
        )}
        <div
          ref={messagesContainerRef}
          className="w-full border flex-grow mb-4 p-4 max-h-[90%] overflow-y-auto rounded-xl"
          hidden={!repoNameValid && !messagesId}
        >
          {messages.length > 0
            ? messages.map((message, index) => (
                <MessageDisplay
                  key={index}
                  index={index}
                  message={message}
                  repoName={repoName}
                  branch={branch}
                  className={
                    index == lastAssistantMessageIndex ? 'bg-slate-700' : ''
                  }
                  onEdit={async (content) => {
                    isStream.current = false
                    setIsLoading(false)

                    const pulls = await parsePullRequests(
                      repoName,
                      content,
                      octokit!
                    )
                    if (pulls.length) {
                      setUserMentionedPullRequest(pulls[pulls.length - 1])
                      setCommitToPR(true)
                    }
                    let newPulls = userMentionedPullRequests
                      ? [...userMentionedPullRequests]
                      : []

                    pulls.forEach((pull1) => {
                      if (
                        !newPulls.some((pull2) =>
                          isPullRequestEqual(pull1, pull2)
                        )
                      ) {
                        newPulls.push(pull1)
                      }
                    })

                    setUserMentionedPullRequests(newPulls)

                    const newMessages: Message[] = [
                      ...messages.slice(0, index),
                      { ...message, content, annotations: { pulls } },
                    ]
                    setMessages(newMessages)
                    setIsCreatingPullRequest(false)
                    if (index == 0) {
                      window.history.pushState({}, "", "/")
                      setMessagesId("")
                      setOriginalSuggestedChanges([])
                      setSuggestedChanges([])
                      setIsProcessingSuggestedChanges(false)
                      setPullRequestTitle(null)
                      setPullRequestBody(null)
                      startStream(content, newMessages, snippets, { pulls })
                    } else {
                      startStream(content, newMessages, snippets, { pulls })
                    }
                  }}
                  commitToPR={commitToPR}
                  setSuggestedChanges={(suggestedChanges) => {
                    setOriginalSuggestedChanges(suggestedChanges)
                    setSuggestedChanges(suggestedChanges)
                  }}
                />
              ))
            : messagesId.length > 0 && (
                <div className="space-y-4">
                  <Skeleton className="h-12 ml-32 rounded-md" />
                  <Skeleton className="h-12 mr-32 rounded-md" />
                  <Skeleton className="h-12 ml-64 rounded-md" />
                  <Skeleton className="h-12 mr-64 rounded-md" />
                </div>
              )}
          {isLoading && (
            <div className="flex justify-around w-full py-2">
              <PulsingLoader size={1.5} />
            </div>
          )}
          {suggestedChanges.length > 0 && (
            <div className="bg-zinc-900 rounded-xl p-4 mt-8">
              <div className="flex justify-between mb-4 align-start">
                <div>
                  <Button
                    className="text-zinc-400 bg-transparent hover:drop-shadow-md hover:bg-initial hover:text-zinc-300 rounded-full p-2 mt-0 pt-0"
                    onClick={() =>
                      applySuggestions(originalSuggestedChanges, commitToPR)
                    }
                    aria-label="Retry applying changes"
                    disabled={isStream.current}
                  >
                    <FaArrowsRotate />
                    &nbsp;&nbsp;Reapply changes
                  </Button>
                  <Button
                    className="text-zinc-400 bg-transparent hover:drop-shadow-md hover:bg-initial hover:text-zinc-300 rounded-full p-2 mt-0 pt-0"
                    onClick={() => {
                      isStream.current = false
                    }}
                    aria-label="Stop"
                    disabled={!isStream.current}
                  >
                    <FaStop />
                    &nbsp;&nbsp;Stop
                  </Button>
                </div>
                <Button
                  className="text-red-400 bg-transparent hover:drop-shadow-md hover:bg-initial hover:text-red-500 rounded-full p-2 mt-0 pt-0"
                  onClick={() => {
                    setSuggestedChanges([])
                    setOriginalSuggestedChanges([])
                  }}
                  aria-label="Unstage Changes"
                >
                  <FaTimes />
                  &nbsp;&nbsp;Unstage Changes
                </Button>
              </div>
              {codeSuggestionsState == 'staging' && (
                <div className="flex justify-around w-full pb-2 mb-4">
                  <p>Staged Changes</p>
                </div>
              )}
              {!suggestedChanges.every(
                (suggestion) => suggestion.state == 'done'
              ) &&
                codeSuggestionsState == 'validating' &&
                !isProcessingSuggestedChanges && (
                  <div className="flex justify-around w-full pb-2 mb-4">
                    Some patches failed to validate, so you may get some
                    unexpected changes. You can try to manually create a PR with
                    the proposed changes. If you think this is an error, feel
                    free to report this to us.
                  </div>
                )}
              {isProcessingSuggestedChanges && (
                <div className="flex justify-around w-full pb-2 mb-4">
                  <p>
                    I&apos;m currently processing and applying these patches,
                    and fixing any errors along the way. This may take a few
                    minutes.
                  </p>
                </div>
              )}
              {isCreatingPullRequest && (
                <div className="flex justify-around w-full pb-2 mb-4">
                  <p>
                    {commitToPR && userMentionedPullRequest
                      ? `Committing to ${userMentionedPullRequest.branch}`
                      : 'Creating pull request...'}
                  </p>
                </div>
              )}
              <div
                style={{
                  opacity: isCreatingPullRequest ? 0.5 : 1,
                  pointerEvents: isCreatingPullRequest ? 'none' : 'auto',
                }}
              >
                {suggestedChanges.map((suggestion, index) => (
                  <div className="fit-content mb-6" key={index}>
                    <div
                      className={`flex justify-between items-center w-full text-sm p-2 px-4 rounded-t-md ${
                        suggestion.state === 'done'
                          ? 'bg-green-900'
                          : suggestion.state === 'error'
                            ? 'bg-red-900'
                            : suggestion.state === 'pending'
                              ? 'bg-zinc-800'
                              : 'bg-yellow-800'
                      }`}
                    >
                      <code>
                        {suggestion.filePath}{' '}
                        {suggestion.state == 'pending' ? (
                          '(pending)'
                        ) : suggestion.state == 'processing' ? (
                          '(processing)'
                        ) : suggestion.state == 'error' ? (
                          '(error)'
                        ) : (
                          <FaCheck
                            style={{ display: 'inline', marginTop: -2 }}
                          />
                        )}
                      </code>
                      {suggestion.error ? (
                        <HoverCard openDelay={300} closeDelay={200}>
                          <HoverCardTrigger>
                            <FaExclamationTriangle
                              className="hover:cursor-pointer ml-2"
                              style={{ marginTop: 2 }}
                            />
                          </HoverCardTrigger>
                          <HoverCardContent className="w-[800px] max-h-[500px] overflow-y-auto">
                            <MarkdownRenderer
                              content={`**This patch could not be directly applied. We're sending the LLM the following message to resolve the error:**\n\n${suggestion.error}`}
                            />
                          </HoverCardContent>
                        </HoverCard>
                      ) : (
                        <Button
                          className="bg-red-800 hover:bg-red-700 text-white"
                          size="sm"
                          onClick={() =>
                            setSuggestedChanges(
                              (suggestedChanges: StatefulCodeSuggestion[]) =>
                                suggestedChanges.filter((s) => s !== suggestion)
                            )
                          }
                        >
                          <FaTrash />
                          &nbsp;Remove
                        </Button>
                      )}
                    </div>
                    {reactCodeMirrors[index]}
                  </div>
                ))}
                {codeSuggestionsState == 'staging' && (
                  <Button
                    className="mt-0 bg-blue-900 text-white hover:bg-blue-800"
                    onClick={() => {
                      setCodeSuggestionsState('validating')
                      applySuggestions(suggestedChanges, commitToPR)
                    }}
                  >
                    <FaCheck />
                    &nbsp;&nbsp;Apply Changes
                  </Button>
                )}
                {(codeSuggestionsState == 'validating' ||
                  codeSuggestionsState == 'creating') && (
                  <>
                    {commitToPR && userMentionedPullRequest ? (
                      <></>
                    ) : (
                      <>
                        <Input
                          value={pullRequestTitle || ''}
                          onChange={(e) => setPullRequestTitle(e.target.value)}
                          placeholder="Pull Request Title"
                          className="w-full mb-4 text-zinc-300"
                          disabled={
                            pullRequestTitle == null ||
                            isProcessingSuggestedChanges
                          }
                        />
                        <Textarea
                          value={pullRequestBody || ''}
                          onChange={(e) => setPullRequestBody(e.target.value)}
                          placeholder="Pull Request Body"
                          className="w-full mb-4 text-zinc-300"
                          disabled={
                            pullRequestTitle == null ||
                            isProcessingSuggestedChanges
                          }
                          rows={8}
                        />
                      </>
                    )}

                    {commitToPR && userMentionedPullRequest ? (
                      <div className="flex grow items-center mb-4">
                        {`You are commiting to ${userMentionedPullRequest.branch}`}
                      </div>
                    ) : (
                      <div className="flex grow items-center mb-4">
                        <Input
                          className="flex items-center w-[600px]"
                          value={baseBranch || ''}
                          onChange={(e) => setBaseBranch(e.target.value)}
                          placeholder="Base Branch"
                          style={{
                            opacity: isProcessingSuggestedChanges ? 0.5 : 1,
                          }}
                        />
                        <FaArrowLeft className="mx-4" />
                        <Input
                          className="flex items-center w-[600px]"
                          value={featureBranch || ''}
                          onChange={(e) => setFeatureBranch(e.target.value)}
                          placeholder="Feature Branch"
                          style={{
                            opacity: isProcessingSuggestedChanges ? 0.5 : 1,
                          }}
                        />
                      </div>
                    )}
                    {commitToPR && userMentionedPullRequest ? (
                      <div className="flex grow items-center mb-4">
                        <Input
                          className="flex items-center w-[600px]"
                          value={commitMessage || ''}
                          onChange={(e) => setCommitMessage(e.target.value)}
                          placeholder="Commit Message"
                          style={{
                            opacity: isProcessingSuggestedChanges ? 0.5 : 1,
                          }}
                        />
                      </div>
                    ) : (
                      <></>
                    )}
                    {!suggestedChanges.every(
                      (suggestion) => suggestion.state == 'done'
                    ) &&
                      !isProcessingSuggestedChanges && (
                        <Alert className="mb-4 bg-yellow-900">
                          <FaExclamationTriangle className="h-4 w-4" />
                          <AlertTitle>Warning</AlertTitle>
                          <AlertDescription>
                            Some patches failed to validate, so you may get some
                            unexpected changes. You can try to manually create a
                            PR with the proposed changes. If you think this is
                            an error, please to report this to us.
                          </AlertDescription>
                        </Alert>
                      )}
                    <Button
                      className="mt-0 bg-blue-900 text-white hover:bg-blue-800"
                      onClick={async () => {
                        setIsCreatingPullRequest(true)
                        setCodeSuggestionsState('creating')
                        const file_changes = suggestedChanges.reduce(
                          (
                            acc: Record<string, string>,
                            suggestion: CodeSuggestion
                          ) => {
                            acc[suggestion.filePath] = suggestion.newCode
                            return acc
                          },
                          {}
                        )
                        try {
                          let response: Response | undefined = undefined
                          console.log('commit topr', commitToPR)
                          if (commitToPR && userMentionedPullRequest) {
                            response = await authorizedFetch(
                              `/backend/commit_to_pull`,
                              {
                                body: JSON.stringify({
                                  repo_name: repoName,
                                  file_changes: file_changes,
                                  pr_number: String(
                                    userMentionedPullRequest?.number
                                  ),
                                  base_branch: baseBranch,
                                  commit_message: commitMessage,
                                }),
                              }
                            )
                          } else {
                            response = await authorizedFetch(
                              `/backend/create_pull`,
                              {
                                body: JSON.stringify({
                                  repo_name: repoName,
                                  file_changes: file_changes,
                                  branch:
                                    'sweep-chat-patch-' +
                                    new Date().toISOString().split('T')[0], // use ai for better branch name, title, and body later
                                  base_branch: baseBranch,
                                  title: pullRequestTitle,
                                  body:
                                    pullRequestBody +
                                    `\n\nSuggested changes from Sweep Chat by @${session?.user?.username}. Continue chatting at ${window.location.origin}/c/${messagesId}.`,
                                }),
                              }
                            )
                          }

                          const data = await response.json()
                          const { pull_request: pullRequest } = data
                          console.log(pullRequest)
                          setPullRequest(pullRequest)
                          setMessages([
                            ...messages,
                            {
                              content: `Pull request created: [https://github.com/${repoName}/pull/${pullRequest.number}](https://github.com/${repoName}/pull/${pullRequest.number})`,
                              role: 'assistant',
                              annotations: {
                                pulls: [pullRequest],
                              },
                            },
                          ])
                          setIsCreatingPullRequest(false)
                          setOriginalSuggestedChanges([])
                          setSuggestedChanges([])
                        } catch (e) {
                          toast({
                            title: 'Error',
                            description: `An error occurred while creating the pull request: ${e}`,
                            variant: 'destructive',
                            duration: Infinity,
                          })
                        }
                      }}
                      disabled={
                        isCreatingPullRequest || isProcessingSuggestedChanges
                      }
                    >
                      {commitToPR && userMentionedPullRequest
                        ? `Commit to Pull Request ${userMentionedPullRequest?.number}`
                        : 'Create Pull Request'}
                    </Button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
        {(repoNameValid || messagesId) && (
          <div className={`flex w-full`}>
            {isStream.current ? (
              <Button
                className="mr-2"
                variant="destructive"
                onClick={async () => {
                  setIsLoading(false)
                  isStream.current = false
                }}
              >
                <FaStop />
                &nbsp;&nbsp;Stop
              </Button>
            ) : (
              <Button
                className="mr-2"
                variant="secondary"
                onClick={async () => {
                  setMessages([])
                  setCurrentMessage('')
                  setIsLoading(false)
                  setSnippets([])
                  setMessagesId('')
                  window.history.pushState({}, '', '/')
                  setSuggestedChanges([])
                  setPullRequest(null)
                  setFeatureBranch(null)
                  setPullRequestTitle(null)
                  setPullRequestBody(null)
                  setUserMentionedPullRequest(null)
                  setUserMentionedPullRequests(null)
                  setCommitToPR(false)
                  setCommitToPRIsOpen(false)
                }}
                disabled={isLoading}
              >
                <FaArrowsRotate />
                &nbsp;&nbsp;Reset
              </Button>
            )}
            <Dialog>
              <DialogTrigger asChild>
                <Button className="mr-2" variant="secondary">
                  <FaShareAlt />
                  &nbsp;&nbsp;Share
                </Button>
              </DialogTrigger>
              <DialogContent className="w-[800px] p-16">
                <h2 className="text-2xl font-bold mb-4 text-center">
                  Share the Conversation
                </h2>
                <p className="text-center">
                  Share your chat session with a team member.
                </p>
                <Input
                  value={`${
                    typeof window !== 'undefined' ? window.location.origin : ''
                  }/c/${messagesId}`}
                  onClick={() => {
                    navigator.clipboard.writeText(
                      `${window.location.origin}/c/${messagesId}`
                    )
                    toast({
                      title: 'Link copied',
                      description:
                        'The link to your current session has been copied to your clipboard.',
                    })
                  }}
                  disabled
                />
                <Button
                  className="mt-2"
                  variant="secondary"
                  onClick={() => {
                    navigator.clipboard.writeText(
                      `${window.location.origin}/c/${messagesId}`
                    )
                    toast({
                      title: 'Link copied',
                      description:
                        'The link to your current session has been copied to your clipboard.',
                    })
                  }}
                >
                  Copy
                </Button>
              </DialogContent>
            </Dialog>
            <Input
              data-ph-capture-attribute-current-message={currentMessage}
              onKeyUp={async (e) => {
                if (e.key === 'Enter') {
                  sendMessage()
                }
              }}
              onChange={(e) => setCurrentMessage(e.target.value)}
              className="p-4"
              value={currentMessage}
              placeholder="Type a message..."
              disabled={isLoading || !repoNameValid || isStream.current}
            />
            <Button
              className="ml-2 bg-blue-900 text-white hover:bg-blue-800"
              variant="secondary"
              onClick={sendMessage}
              disabled={isLoading}
            >
              <FaPaperPlane />
              &nbsp;&nbsp;Send
            </Button>
          </div>
        )}
      </main>
    </>
  )
}

export default function WrappedApp({
  session,
  ...props
}: {
  session: Session | null
  [key: string]: any
}) {
  return (
    <PostHogProvider>
      <SessionProvider session={session}>
        <App {...props} />
      </SessionProvider>
    </PostHogProvider>
  )
}
