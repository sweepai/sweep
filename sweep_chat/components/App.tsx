'use client'

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { Input } from '../components/ui/input'
import {
  FaArrowLeft,
  FaCheck,
  FaChevronDown,
  FaCog,
  FaComments,
  FaExclamationTriangle,
  FaGithub,
  FaPaperPlane,
  FaPlus,
  FaShareAlt,
  FaSignOutAlt,
  FaStop,
  FaTimes,
  FaTrash,
  FaCodeBranch,
} from 'react-icons/fa'
import { FaArrowsRotate, FaCodeCommit } from 'react-icons/fa6'
import { Button } from '@/components/ui/button'
import { useLocalStorage } from 'usehooks-ts'
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card'
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuList,
  NavigationMenuTrigger,
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
  DEFAULT_K,
  DEFAULT_MODEL,
  modelMap,
} from '@/lib/constants'
import {
  Repository,
  Snippet,
  PullRequest,
  Message,
  CodeSuggestion,
  StatefulCodeSuggestion,
  ChatSummary,
  PrValidationStatus,
  SnakeCaseKeys,
} from '@/lib/types'

import { Octokit } from 'octokit'
import {
  truncate,
  toCamelCaseKeys,
  toSnakeCaseKeys,
} from '@/lib/str_utils'
import {
  MarkdownRenderer,
} from './shared/MarkdownRenderer'
import { ContextSideBar } from './shared/ContextSideBar'
import parsePullRequests from '@/lib/parsePullRequest'

import { debounce } from 'lodash'
import { formatDistanceToNow } from 'date-fns'
import { streamResponseMessages } from '@/lib/streamingUtils'
import { Alert, AlertDescription, AlertTitle } from './ui/alert'
import { Skeleton } from './ui/skeleton'
import { isPullRequestEqual } from '@/lib/pullUtils'
import CodeMirrorEditor from './CodeMirrorSuggestionEditor'
// @ts-ignore
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from './ui/resizable'
import MessageDisplay from './MessageDisplay'
import { withLoading } from '@/lib/contextManagers'


function App({ defaultMessageId = '' }: { defaultMessageId?: string }) {
  const [repoName, setRepoName] = useState<string>('')
  const [branch, setBranch] = useState<string>('main')
  const [repoNameValid, setRepoNameValid] = useState<boolean>(false)
  const [repoNameDisabled, setRepoNameDisabled] = useState<boolean>(false)

  const [k, setK] = useLocalStorage<number>('k', DEFAULT_K)
  const [model, setModel] = useLocalStorage<keyof typeof modelMap>(
    'model',
    DEFAULT_MODEL
  )
  const [snippets, setSnippets] = useState<Snippet[]>([])
  const [searchMessage, setSearchMessage] = useState<string>('')
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

  const [isValidatingPR, setIsValidatingPR] = useState<boolean>(false)
  const [prValidationStatuses, setPrValidationStatuses] = useState<
    PrValidationStatus[]
  >([])

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
    (url: string, body: Record<string, any> = {}, options: RequestInit = {}) => {
      return fetch(`/backend/${url}`, {
        method: options.method || 'POST',
        headers: {
          ...options.headers,
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.user.accessToken}`,
        },
        body: (body && options.method != "GET") ? JSON.stringify({
          repo_name: repoName,
          ...body
        }) : undefined,
        ...options,
      })
    },
    [session?.user.accessToken, repoName]
  )

  useEffect(() => {
    if (
      messagesId &&
      !previousChats.some((chat) => chat.messagesId === messagesId) &&
      messages.length > 0
    ) {
      setPreviousChats([
        ...previousChats,
        {
          messagesId: messagesId,
          createdAt: new Date().toISOString(),
          initialMessage: messages[0].content,
        },
      ])
    }
  }, [messagesId, messages.length])

  useEffect(() => {
    if (messagesId) {
      window.history.pushState({}, '', `/c/${messagesId}`)
    }
  }, [messagesId])

  useEffect(() => {
    console.log('loading message', messagesId)
    if (messagesId) {
      ;(async () => {
        const response = await authorizedFetch(
          `/messages/load/${messagesId}`,
          {},
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
            `Loaded ${messages.length} messages from ${messagesId}`
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
      if (scrollHeight - scrollTop - clientHeight < 120) {
        messagesContainerRef.current.scrollTop =
          messagesContainerRef.current.scrollHeight
      }
    }
  }, [messages, isValidatingPR, prValidationStatuses])

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

  useEffect(() => {
    if (messages.length > 0 && userMentionedPullRequests?.length == 0) {
      for (const message of messages) {
        if (message.role == 'assistant' && message.annotations?.pulls) {
          setUserMentionedPullRequests(message.annotations.pulls)
          setBranch(message.annotations.pulls[0].branch)
          setBaseBranch(message.annotations.pulls[0].branch)
        }
      }
    }
  }, [messages])

  const save = async (
    repoName: string,
    messages: Message[],
    snippets: Snippet[],
    messagesId: string,
    userMentionedPullRequest: PullRequest | null = null,
    userMentionedPullRequests: PullRequest[] | null = null,
    commitToPR: boolean = false,
    originalSuggestedChanges: StatefulCodeSuggestion[],
    suggestedChanges: StatefulCodeSuggestion[],
    pullRequest: PullRequest | null = null,
    pullRequestTitle: string | null = null,
    pullRequestBody: string | null = null
  ) => {
    const commitToPRString: string = commitToPR ? 'true' : 'false'
    const saveResponse = await authorizedFetch('/messages/save', toSnakeCaseKeys({
      repoName,
      messages,
      snippets,
      messageId: messagesId,
      originalCodeSuggestions: originalSuggestedChanges,
      codeSuggestions: suggestedChanges,
      pullRequest,
      pullRequestTitle,
      pullRequestBody,
      userMentionedPullRequest,
      userMentionedPullRequests,
      commitToPRString,
    }))
    const saveData = await saveResponse.json()
    console.log(`Saving ${messages.length} messages to ${messagesId}`)
    if (saveData.status == 'success') {
      const { message_id } = saveData
      if (!messagesId && message_id) {
        setMessagesId(message_id)
        const updatedUrl = `/c/${message_id}`
      }
    } else {
      console.warn('Failed to save message', saveData)
    }
  }

  const debouncedSave = useCallback(
    debounce((...args: Parameters<typeof save>) => {
      save(
        ...args
      )
    },
    2000,
    { leading: true, maxWait: 5000 }
    ), []
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

  const posthog_capture = useCallback((event: string, metadata: Record<string, any> = {}) => {
    posthog.capture(event, {
      repoName,
      messages,
      snippets,
      messagesId,
      ...metadata,
    })
  }, [repoName, messages, snippets, messagesId])

  const reactCodeMirrors = suggestedChanges.map((suggestion, index) => (
    <CodeMirrorEditor
      suggestion={suggestion}
      index={index}
      setSuggestedChanges={setSuggestedChanges}
      key={index}
    />
  ))

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
    let currentCodeSuggestions: StatefulCodeSuggestion[] = codeSuggestions.map(
      (suggestion) => ({
        ...suggestion,
        state: 'pending',
      })
    )
    setSuggestedChanges(currentCodeSuggestions)
    setIsProcessingSuggestedChanges(true)
    ;(async () => {
      console.log(userMentionedPullRequest)
      const streamedResponse = await authorizedFetch(`/autofix`, {
        code_suggestions: codeSuggestions.map(toSnakeCaseKeys),
        branch: commitToPR ? userMentionedPullRequest?.branch : baseBranch,
      })

      // TODO: casing should be automatically handled

      try {
        for await (const currentState of streamResponseMessages(
          streamedResponse,
          isStream,
          5 * 60 * 1000
        )) {
          // console.log(currentState)
          if (currentState.error) {
            throw new Error(currentState.error)
          }
          currentCodeSuggestions = currentState.map(toCamelCaseKeys)
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
        posthog_capture('auto fix error', {
          error: e.message,
        })
      } finally {
        isStream.current = false
        setIsProcessingSuggestedChanges(false)

        if (!featureBranch || !pullRequestTitle || !pullRequestBody) {
          const prMetadata = await authorizedFetch(
            '/create_pull_metadata',
            {
              repo_name: repoName,
              modify_files_dict: suggestedChanges.reduce((
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
              messages,
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

  const scrollToBottom = (timeout = 0) => {
    setTimeout(() => {
      if (messagesContainerRef.current) {
        messagesContainerRef.current.scrollTop =
          messagesContainerRef.current.scrollHeight
      }
    }, timeout)
  }

  const startChatStream = async (
    message: string,
    newMessages: Message[],
    snippets: Snippet[],
    annotations: { pulls: PullRequest[] } = { pulls: [] }
  ) => {
    setIsLoading(true)
    var currentSnippets = snippets
    if (currentSnippets.length == 0) {
      await withLoading(setIsLoading, async () => {
        const snippetsResponse = await authorizedFetch(`/search`, {
          repo_name: repoName,
          query: message,
          annotations,
          branch: baseBranch,
        })

        let streamedMessage: string = ''
        for await (const chunk of streamResponseMessages(snippetsResponse, isStream)) {
          streamedMessage = chunk[0]
          currentSnippets = chunk[1]
          currentSnippets = currentSnippets.slice(0, k)
          setSnippets(currentSnippets)
          setSearchMessage(streamedMessage)
        }
        setSearchMessage('')
        if (!currentSnippets.length) {
          throw new Error('No snippets found')
        }
      }, (error) => {
        toast({
          title: 'Failed to search codebase',
          description: `The following error has occurred: ${error.message}. Sometimes, logging out and logging back in can resolve this issue.`,
          variant: 'destructive',
          duration: Infinity,
        })
        posthog_capture('chat errored', {
          error: error.message,
        })
      })
    }

    // Stream
    let streamedMessages: Message[] = []
    let respondedMessages: Message[] = [
      ...newMessages,
      { content: 'Loading...', role: 'assistant' } as Message,
    ]
    setMessages(respondedMessages)

    await withLoading(setIsLoading, async () => {
      const chatResponse = await authorizedFetch('/chat', {
        messages: newMessages,
        snippets: currentSnippets,
        model,
        branch: baseBranch,
        k,
      })
      let messageLength = newMessages.length
      for await (const patches of streamResponseMessages(chatResponse, isStream)) {
        for (const patch of patches) {
          if (patch.op == 'error') {
            throw new Error(patch.value)
          }
        }
        try {
          streamedMessages = jsonpatch.applyPatch(
            streamedMessages,
            patches
          ).newDocument
        } catch (e: any) {
          console.log(patches)
          console.warn(e)
          continue
        }
        setMessages([...newMessages, ...streamedMessages])
        if (streamedMessages.length > messageLength) {
          messageLength = streamedMessages.length
        }
      }
    }, (e) => {
      console.error(e)
      toast({
        title: 'Chat stream failed',
        description: e.message,
        variant: 'destructive',
        duration: Infinity,
      })
      setIsLoading(false)
      posthog_capture('chat errored', {
        error: e.message,
      })
      throw e
    })

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
    posthog_capture('chat succeeded')
  }

  const sendMessage = async () => {
    posthog_capture('chat submitted')
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
    startChatStream(currentMessage, newMessages, snippets, { pulls })
  }

  const validatePr = async (pr: PullRequest, index: number) => {
    // TODO: put repo name into every body and make it all jsonified
    setPrValidationStatuses([])
    setIsValidatingPR(true)
    withLoading(setIsValidatingPR, async () => {
      const response = await authorizedFetch(`/validate_pull`, {
        pull_request_number: pr.number,
      })
      let scrolledToBottom = false
      let currentPrValidationStatuses: PrValidationStatus[] = []
      setMessages([
        ...messages.slice(0, index),
        {
          ...messages[index],
          annotations: {
            ...messages[index].annotations,
            prValidationStatuses: currentPrValidationStatuses,
          },
        },
        ...messages.slice(index + 1),
      ])
      for await (const streamedPrValidationStatuses of streamResponseMessages(
        response,
        isStream
      )) {
        currentPrValidationStatuses = streamedPrValidationStatuses.map(
          (status: SnakeCaseKeys<PrValidationStatus>) => toCamelCaseKeys(status)
        )
        setMessages([
          ...messages.slice(0, index),
          {
            ...messages[index],
            annotations: {
              ...messages[index].annotations,
              prValidationStatuses: currentPrValidationStatuses,
            },
          },
          ...messages.slice(index + 1),
        ])
        if (!scrolledToBottom) {
          scrollToBottom(100)
          scrolledToBottom = true
        }
      }

      const prFailed = currentPrValidationStatuses.some(
        (status: PrValidationStatus) =>
          status.status == 'failure' && status.stdout.length > 0
      )
      console.log(prFailed) // TODO: make this automatically run the fix
      if (prFailed) {
        fixPrValidationErrors(currentPrValidationStatuses)
      }
    }, (error) => toast({
        title: 'Error validating PR',
        description: `Please try again later. ${error.message}`,
        variant: 'destructive',
      })
    )
  }

  const fixPrValidationErrors = async (
    prValidationStatuses: PrValidationStatus[]
  ) => {
    const failedPrValidationStatuses = prValidationStatuses?.find(
      (status) => status.status === 'failure' && status.stdout.length > 0
    )
    // sometimes theres no stdout for some reason, will look into this
    if (!failedPrValidationStatuses) {
      toast({
        title: 'No failed PR checks.',
        description: 'Please try again later.',
        variant: 'destructive',
      })
      return
    }
    const content = `Help me fix the following CI/CD pipeline errors:\n\`\`\`\n${failedPrValidationStatuses?.stdout}\n\`\`\``

    setMessages((currentMessages) => {
      const newMessages: Message[] = [
        ...currentMessages,
        {
          role: 'user',
          content: content,
        },
      ]
      startChatStream(content, newMessages, snippets)
      return newMessages
    })
  }

  const reset = () => {
    setMessages([])
    setCurrentMessage('')
    setIsLoading(false)
    setSnippets([])
    setMessagesId('')
    setSuggestedChanges([])
    setPullRequest(null)
    setFeatureBranch(null)
    setPullRequestTitle(null)
    setPullRequestBody(null)
    setUserMentionedPullRequest(null)
    setUserMentionedPullRequests(null)
    setCommitToPR(false)
    setCommitToPRIsOpen(false)
  }

  return (
    <>
      <main className="flex h-screen flex-col items-center justify-between p-12 pt-20">
        <NavigationMenu className="fixed top-0 left-0 w-[100vw] px-4">
          <div className="flex items-center justify-between w-[100vw] mb-2 align-center">
            <div className="flex items-center gap-4">
              <img
                src="/banner.svg"
                width={140}
                height={200}
                alt="Sweep AI Logo"
                className="h-20 rounded-lg hover:cursor-pointer box-shadow-md"
                onClick={() => {
                  window.location.href = '/'
                }}
                style={{
                  marginTop: 2,
                }}
              />
              <DropdownMenu>
                <DropdownMenuTrigger className="outline-none">
                  <p className="text-sm font-bold flex items-center">
                    Previous Chats <FaChevronDown className="ml-2" />
                  </p>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="center" className="mt-2">
                  {previousChats.length > 0 ? (
                    previousChats
                      .sort(
                        (a, b) =>
                          new Date(b.createdAt).getTime() -
                          new Date(a.createdAt).getTime()
                      )
                      .slice(0, 10)
                      .map((chat) => (
                        <DropdownMenuItem
                          key={chat.messagesId}
                          className="hover:cursor-pointer"
                          onClick={() => {
                            setMessagesId(chat.messagesId)
                            window.location.href = `/c/${chat.messagesId}`
                          }}
                          disabled={chat.messagesId === messagesId}
                        >
                          <b>{truncate(chat.initialMessage, 80)}</b>
                          &nbsp;created{' '}
                          {formatDistanceToNow(new Date(chat.createdAt), {
                            addSuffix: true,
                          })}
                        </DropdownMenuItem>
                      ))
                  ) : (
                    <DropdownMenuItem>No history</DropdownMenuItem>
                  )}
                </DropdownMenuContent>
                {/* Warning: these message IDs are stored in local storage.
                  If you want to delete them, you will need to clear your browser cache. */}
              </DropdownMenu>
            </div>
            <NavigationMenuList className="w-full flex justify-between">
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="outline" className="ml-4">
                    <FaCog className="mr-2" />
                    Settings
                  </Button>
                </DialogTrigger>
                <DialogContent className="w-120 p-16">
                  <h2 className="text-2xl font-bold mb-4 text-center">
                    Settings
                  </h2>
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
          } grow`}
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
              var data = null;
              await withLoading(setRepoNameDisabled, async () => {
                const response = await authorizedFetch(
                  `/repo?repo_name=${cleanedRepoName}`,
                  {},
                  {
                    method: 'GET',
                  }
                )
                data = await response.json()
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
                if (octokit) {
                  const repo = await octokit.rest.repos.get({
                    owner: cleanedRepoName.split('/')[0],
                    repo: cleanedRepoName.split('/')[1],
                  })
                  setBranch(repo.data.default_branch)
                  setBaseBranch(repo.data.default_branch)
                }
                reset()
              }, (error) => {
                setRepoNameValid(false)
                toast({
                  title: 'Failed to load repository',
                  description: error.message,
                  variant: 'destructive',
                  duration: Infinity,
                })
              });
            }}
          />
          <Input
            placeholder="Branch"
            className="ml-4 w-[500px]"
            value={baseBranch}
            onChange={(e) => setBaseBranch(e.target.value)}
          />
        </div>

        {(repoNameValid || messagesId) && (
          <ResizablePanelGroup direction="horizontal">
            <ResizablePanel defaultSize={25} className="pr-4">
              <ContextSideBar
                snippets={snippets}
                setSnippets={setSnippets}
                repoName={repoName}
                branch={branch}
                k={k}
                searchMessage={searchMessage}
              />
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={75} className="pl-4 flex flex-col">
              <div
                ref={messagesContainerRef}
                className="h-full w-full border flex-grow mb-4 p-4 overflow-y-auto rounded-xl"
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
                          index == lastAssistantMessageIndex
                            ? 'bg-slate-700'
                            : ''
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
                          let newPulls =
                            userMentionedPullRequests && index > 0
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

                          setUserMentionedPullRequests(
                            newPulls.length > 0 ? newPulls : null
                          )

                          if (newPulls.length > 0) {
                            setUserMentionedPullRequest(
                              newPulls[newPulls.length - 1]
                            )
                          } else {
                            setUserMentionedPullRequest(null)
                            setCommitToPR(false)
                          }

                          const newMessages: Message[] = [
                            ...messages.slice(0, index),
                            { ...message, content, annotations: { pulls } },
                          ]
                          setMessages(newMessages)
                          setIsCreatingPullRequest(false)
                          if (index == 0) {
                            setMessagesId('')
                            setOriginalSuggestedChanges([])
                            setSuggestedChanges([])
                            setIsProcessingSuggestedChanges(false)
                            setPullRequestTitle(null)
                            setPullRequestBody(null)
                            startChatStream(content, newMessages, snippets, {
                              pulls,
                            })
                            setPrValidationStatuses([])
                          } else {
                            startChatStream(content, newMessages, snippets, {
                              pulls,
                            })
                          }
                        }}
                        commitToPR={commitToPR}
                        setSuggestedChanges={(suggestedChanges) => {
                          setOriginalSuggestedChanges(suggestedChanges)
                          setSuggestedChanges(suggestedChanges)
                        }}
                        onValidatePR={(pr) => validatePr(pr, index)}
                        fixPrValidationErrors={() => {
                          const currentPrValidationStatuses =
                            messages[index]!.annotations!.prValidationStatuses
                          if (currentPrValidationStatuses) {
                            fixPrValidationErrors(currentPrValidationStatuses)
                          }
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
                      <div className="flex items-center align-middle">
                        <NavigationMenu>
                          <NavigationMenuList>
                            <NavigationMenuItem>
                              <NavigationMenuTrigger className="bg-secondary hover:bg-secondary mr-2">
                                {userMentionedPullRequest && commitToPR ? (
                                  <span className="text-sm w-full p-2">
                                    <FaCodeCommit
                                      style={{ display: 'inline' }}
                                    />
                                    &nbsp;&nbsp;Commit to PR #
                                    {userMentionedPullRequest.number}
                                  </span>
                                ) : (
                                  <span className="text-sm w-full p-2">
                                    <FaCodeBranch
                                      style={{ display: 'inline' }}
                                    />
                                    &nbsp;&nbsp;Create New PR
                                  </span>
                                )}
                              </NavigationMenuTrigger>
                              <NavigationMenuContent className="w-full">
                                {commitToPR && (
                                  <Button
                                    className="w-full p-2 px-4"
                                    variant="secondary"
                                    disabled={isLoading}
                                    onClick={() => {
                                      setCommitToPR(false)
                                      setCommitToPRIsOpen(false)
                                    }}
                                  >
                                    <FaCodeBranch
                                      style={{ display: 'inline' }}
                                    />
                                    &nbsp;&nbsp;Create New PR
                                  </Button>
                                )}
                                {// loop through all pull requests
                                userMentionedPullRequests?.map((pr, index) => {
                                  // dont show current selected pr, unless we are creating a pr rn
                                  if (
                                    pr.number !==
                                      userMentionedPullRequest?.number ||
                                    !commitToPR
                                  ) {
                                    return (
                                      <Button
                                        className="w-full p-2 px-4"
                                        variant="secondary"
                                        disabled={isLoading}
                                        onClick={() => {
                                          setCommitToPR(true)
                                          setUserMentionedPullRequest(pr)
                                          setCommitToPRIsOpen(false)
                                        }}
                                        key={index}
                                      >
                                        <FaCodeCommit
                                          style={{ display: 'inline' }}
                                        />
                                        &nbsp;&nbsp;Commit to PR #{pr.number}
                                      </Button>
                                    )
                                  }
                                })}
                              </NavigationMenuContent>
                            </NavigationMenuItem>
                          </NavigationMenuList>
                        </NavigationMenu>
                        <Button
                          className="text-zinc-400 bg-transparent hover:drop-shadow-md hover:bg-initial hover:text-zinc-300 rounded-full px-2 mt-0"
                          onClick={() =>
                            applySuggestions(
                              originalSuggestedChanges,
                              commitToPR
                            )
                          }
                          aria-label="Retry applying changes"
                          disabled={isStream.current}
                        >
                          <FaArrowsRotate />
                          &nbsp;&nbsp;Reapply changes
                        </Button>
                        <Button
                          className="text-zinc-400 bg-transparent hover:drop-shadow-md hover:bg-initial hover:text-zinc-300 rounded-full px-2 mt-0"
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
                        className="text-red-400 bg-transparent hover:drop-shadow-md hover:bg-initial hover:text-red-500 rounded-full px-2 mt-0"
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
                        <p className="font-bold">Staged Changes</p>
                      </div>
                    )}
                    {!suggestedChanges.every(
                      (suggestion) => suggestion.state == 'done'
                    ) &&
                      codeSuggestionsState == 'validating' &&
                      !isProcessingSuggestedChanges && (
                        <div className="flex justify-around w-full pb-2 mb-4">
                          Some patches failed to validate, so you may get some
                          unexpected changes. You can try to manually create a
                          PR with the proposed changes. If you think this is an
                          error, feel free to report this to us.
                        </div>
                      )}
                    {isProcessingSuggestedChanges && (
                      <div className="flex justify-around w-full pb-2 mb-4">
                        <p>
                          I&apos;m currently processing and applying these
                          patches, and fixing any errors along the way. This may
                          take a few minutes.
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
                            <div className="flex justify-end items-center">
                              {suggestion.error && (
                                <HoverCard openDelay={300} closeDelay={200}>
                                  <HoverCardTrigger>
                                    <FaExclamationTriangle
                                      className="hover:cursor-pointer mr-4 text-yellow-500"
                                      style={{ marginTop: 2 }}
                                    />
                                  </HoverCardTrigger>
                                  <HoverCardContent className="w-[800px] max-h-[500px] overflow-y-auto">
                                    <MarkdownRenderer
                                      content={`**This patch could not be directly applied. We're sending the LLM the following message to resolve the error:**\n\n${suggestion.error}`}
                                    />
                                  </HoverCardContent>
                                </HoverCard>
                              )}
                              <Button
                                className="bg-red-800 hover:bg-red-700 text-white"
                                size="sm"
                                onClick={() =>
                                  setSuggestedChanges(
                                    (
                                      suggestedChanges: StatefulCodeSuggestion[]
                                    ) =>
                                      suggestedChanges.filter(
                                        (s) => s !== suggestion
                                      )
                                  )
                                }
                              >
                                <FaTrash />
                                &nbsp;Remove
                              </Button>
                            </div>
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
                          {!(commitToPR && userMentionedPullRequest) && (
                            <>
                              <Input
                                value={pullRequestTitle || ''}
                                onChange={(e) =>
                                  setPullRequestTitle(e.target.value)
                                }
                                placeholder="Pull Request Title"
                                className="w-full mb-4 text-zinc-300"
                                disabled={
                                  pullRequestTitle == null ||
                                  isProcessingSuggestedChanges
                                }
                              />
                              <Textarea
                                value={pullRequestBody || ''}
                                onChange={(e) =>
                                  setPullRequestBody(e.target.value)
                                }
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
                              {`You are commiting to ${userMentionedPullRequest.branch} with the following commit message:`}
                            </div>
                          ) : (
                            <div className="flex grow items-center mb-4">
                              <Input
                                className="flex items-center w-[600px]"
                                value={baseBranch || ''}
                                onChange={(e) => setBaseBranch(e.target.value)}
                                placeholder="Base Branch"
                                style={{
                                  opacity: isProcessingSuggestedChanges
                                    ? 0.5
                                    : 1,
                                }}
                              />
                              <FaArrowLeft className="mx-4" />
                              <Input
                                className="flex items-center w-[600px]"
                                value={featureBranch || ''}
                                onChange={(e) =>
                                  setFeatureBranch(e.target.value)
                                }
                                placeholder="Feature Branch"
                                style={{
                                  opacity: isProcessingSuggestedChanges
                                    ? 0.5
                                    : 1,
                                }}
                              />
                            </div>
                          )}
                          {commitToPR && userMentionedPullRequest ? (
                            <div className="flex grow items-center mb-4">
                              <Input
                                className="flex items-center w-[600px]"
                                value={pullRequestTitle || ''}
                                onChange={(e) =>
                                  setPullRequestTitle(e.target.value)
                                }
                                placeholder="Commit message"
                                style={{
                                  opacity: isProcessingSuggestedChanges
                                    ? 0.5
                                    : 1,
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
                                  Some patches failed to validate, so you may
                                  get some unexpected changes. You can try to
                                  manually create a PR with the proposed
                                  changes. If you think this is an error, please
                                  to report this to us.
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
                                    `/commit_to_pull`,
                                    {
                                      file_changes: file_changes,
                                      pr_number: String(
                                        userMentionedPullRequest?.number
                                      ),
                                      base_branch: baseBranch,
                                      commit_message: pullRequestTitle,
                                    }
                                  )
                                } else {
                                  response = await authorizedFetch(
                                    `/backend/create_pull`,
                                    {
                                      file_changes: file_changes,
                                      branch:
                                        'sweep-chat-patch-' +
                                        new Date()
                                          .toISOString()
                                          .split('T')[0], // use ai for better branch name, title, and body later
                                      base_branch: baseBranch,
                                      title: pullRequestTitle,
                                      body:
                                        pullRequestBody +
                                        `\n\nSuggested changes from Sweep Chat by @${session?.user?.username}. Continue chatting at ${window.location.origin}/c/${messagesId}.`,
                                    }
                                  )
                                }

                                const data = await response.json()
                                const {
                                  pull_request: pullRequest,
                                  new_branch: branch,
                                } = data
                                pullRequest.branch = branch
                                console.log('pullrequest', pullRequest)
                                setPullRequest(pullRequest)
                                setUserMentionedPullRequest(pullRequest)
                                let newPulls = userMentionedPullRequests
                                  ? [...userMentionedPullRequests]
                                  : []

                                newPulls.forEach((pull) => {
                                  if (!isPullRequestEqual(pull, pullRequest)) {
                                    newPulls.push(pullRequest)
                                  }
                                })

                                setUserMentionedPullRequests(newPulls)

                                // for commits, show a different message
                                const newMessages: Message[] = [
                                  ...messages,
                                  {
                                    content: `Pull request created: [https://github.com/${repoName}/pull/${pullRequest.number}](https://github.com/${repoName}/pull/${pullRequest.number})`,
                                    role: 'assistant',
                                    annotations: {
                                      pulls: [pullRequest],
                                    },
                                  },
                                ]
                                console.log(pullRequest)
                                setPullRequest(pullRequest)
                                setMessages(newMessages)
                                setIsCreatingPullRequest(false)
                                setOriginalSuggestedChanges([])
                                setSuggestedChanges([])

                                validatePr(pullRequest, newMessages.length - 1)
                              } catch (e) {
                                setIsCreatingPullRequest(false)
                                toast({
                                  title: 'Error',
                                  description: `An error occurred while creating the pull request: ${e}`,
                                  variant: 'destructive',
                                  duration: Infinity,
                                })
                              }
                            }}
                            disabled={
                              isCreatingPullRequest ||
                              isProcessingSuggestedChanges ||
                              !pullRequestTitle ||
                              !pullRequestBody
                            }
                          >
                            {commitToPR && userMentionedPullRequest
                              ? `Commit to Pull Request #${userMentionedPullRequest?.number}`
                              : 'Create Pull Request'}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
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
                    onClick={reset}
                    disabled={isLoading}
                  >
                    <FaPlus />
                    &nbsp;&nbsp;New Chat
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
                        typeof window !== 'undefined'
                          ? window.location.origin
                          : ''
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
                <Textarea
                  data-ph-capture-attribute-current-message={currentMessage}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && e.shiftKey) {
                      e.currentTarget.style.height = `${e.currentTarget.scrollHeight / 2}px`
                    }
                    if (
                      e.key === 'Enter' &&
                      !e.shiftKey &&
                      currentMessage.trim().length > 0
                    ) {
                      sendMessage()
                      // @ts-ignore
                      e.target.style!.height = 'auto'
                      // @ts-ignore
                      e.target.style!.height = `42px`
                      e.stopPropagation()
                      e.preventDefault()
                    }
                  }}
                  onChange={(e) => {
                    setCurrentMessage(e.target.value)
                    e.target.style.height = `${e.target.scrollHeight}px`
                  }}
                  className="p-2 overflow-y-hidden"
                  style={{ minHeight: 24, height: 42 }}
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
            </ResizablePanel>
          </ResizablePanelGroup>
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
