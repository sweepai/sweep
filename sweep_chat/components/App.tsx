"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "../components/ui/input"
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { dracula } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { FaCheck, FaCog, FaGithub, FaPencilAlt, FaShareAlt, FaStop } from "react-icons/fa";
import { FaArrowsRotate } from "react-icons/fa6";
import { Button } from "@/components/ui/button";
import { useLocalStorage } from "usehooks-ts";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { AutoComplete } from "@/components/ui/autocomplete";
import { Toaster } from "@/components/ui/toaster";
import { toast } from "@/components/ui/use-toast";
import { useSession, signIn, SessionProvider, signOut } from "next-auth/react";
import { Session } from "next-auth";
import { PostHogProvider, usePostHog } from "posthog-js/react";
import posthog from "posthog-js";
import Survey from "./Survey";
import * as jsonpatch from 'fast-json-patch';
import { ReadableStreamDefaultReadResult } from "stream/web";
import { Textarea } from "./ui/textarea";
import { Slider } from "./ui/slider";
import { Dialog, DialogContent, DialogTrigger } from "./ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { Label } from "./ui/label";
import PulsingLoader from "./shared/PulsingLoader";

import { Octokit } from "octokit";

const codeStyle = dracula;

if (typeof window !== 'undefined') {
  posthog.init(
    process.env.NEXT_PUBLIC_POSTHOG_KEY!,
    {
      api_host: "/ingest",
      ui_host: "https://us.posthog.com"
    }
  )
  posthog.debug(false)
}

type Repository = any;

interface Snippet {
  content: string;
  start: number;
  end: number;
  file_path: string;
  type_name: "source" | "tests" | "dependencies" | "tools" | "docs";
  score: number;
}

interface FileDiff {
  sha: string;
  filename: string;
  status: "modified" | "added" | "removed" | "renamed" | "copied" | "changed" | "unchanged";
  additions: number;
  deletions: number;
  changes: number;
  blob_url: string;
  raw_url: string;
  contents_url: string;
  patch?: string | undefined;
  previous_filename?: string | undefined;
}

interface PullRequest {
  number: number;
  repo_name: string;
  title: string;
  body: string;
  labels: string[];
  status: string;
  file_diffs: FileDiff[]
}

interface Message {
  content: string; // This is the message content or function output
  role: "user" | "assistant" | "function";
  function_call?: {
    function_name: string;
    function_parameters: Record<string, any>;
    is_complete: boolean;
    snippets?: Snippet[];
  }; // This is the function input
  annotations?: {
    pulls?: PullRequest[]
  }
}

const modelMap: Record<string, string> = {
  "claude-3-opus-20240229": "Opus",
  "claude-3-sonnet-20240229": "Sonnet",
  "claude-3-haiku-20240307": "Haiku",
  "gpt-4o": "GPT-4o",
}

const DEFAULT_K: number = 8

const sliceLines = (content: string, start: number, end: number) => {
  return content.split("\n").slice(Math.max(start - 1, 0), end).join("\n");
}

const MarkdownRenderer = ({ content, className }: { content: string, className?: string }) => {
  return (
    <Markdown
      className={`${className} reactMarkdown`}
      remarkPlugins={[remarkGfm]}
      components={{
        code(props) {
          const { children, className, node, ref, ...rest } = props
          const match = /language-(\w+)/.exec(className || '')
          return match ? (
            <SyntaxHighlighter
              {...rest} // eslint-disable-line
              PreTag="div"
              language={match[1]}
              style={codeStyle}
              customStyle={{
                backgroundColor: '#333',
              }}
              className="rounded-xl"
            >
              {String(children).replace(/\n$/, '')}
            </SyntaxHighlighter>
          ) : (
            <code
              {...rest}
              className={`rounded-xl ${className}`}
            >
              {children}
            </code>
          )
        }
      }}
    >
      {content}
    </Markdown>
  )
}

const typeNameToColor = {
  "source": "bg-blue-900",
  "tests": "bg-green-900",
  "dependencies": "bg-zinc-600",
  "tools": "bg-purple-900",
  "docs": "bg-yellow-900",
}

const SnippetBadge = ({
  snippet,
  className,
  button,
}: {
  snippet: Snippet;
  className?: string;
  button?: JSX.Element;
}) => {
  return (
    <HoverCard openDelay={300} closeDelay={200}>
      <div className={`p-2 rounded-xl mb-2 text-xs inline-block mr-2 ${typeNameToColor[snippet.type_name]} ${className || ""} `} style={{ opacity: `${Math.max(Math.min(1, snippet.score), 0.2)}` }}>
        <HoverCardTrigger asChild>
          <Button variant="link" className="text-sm py-0 px-1 h-6 leading-4">
            <span>
              {snippet.end > snippet.content.split('\n').length - 3 && snippet.start == 0 ?
                snippet.file_path : `${snippet.file_path}:${snippet.start}-${snippet.end}`
              }
            </span>
            {
              snippet.type_name !== "source" && (
                <code className="ml-2 bg-opacity-20 bg-black text-white rounded p-1 px-2 text-xs">{snippet.type_name}</code>
              )
            }
          </Button>
        </HoverCardTrigger>
      </div>
      <HoverCardContent className="w-[800px] mr-2" style={{ opacity: 1 }}>
        <SyntaxHighlighter
          PreTag="div"
          language="python"
          style={codeStyle}
          customStyle={{
            backgroundColor: 'transparent',
            whiteSpace: 'pre-wrap',
          }}
          className="rounded-xl max-h-80 overflow-y-auto p-4 w-full"
        >
          {sliceLines(snippet.content, snippet.start, snippet.end)}
        </SyntaxHighlighter>
      </HoverCardContent>
    </HoverCard>
  )
}

const getFunctionCallHeaderString = (functionCall: Message["function_call"]) => {
switch (functionCall?.function_name) {
  case "analysis":
    return functionCall.is_complete ? "Analysis" : "Analyzing..."
  case "self_critique":
    return functionCall.is_complete ? "Self critique" : "Self critiquing..."
  case "search_codebase":
    if (functionCall!.function_parameters?.query) {
      return functionCall.is_complete ? `Search codebase for "${functionCall.function_parameters.query.trim()}"` : `Searching codebase for "${functionCall.function_parameters.query.trim()}"...`
    } else {
      return functionCall.is_complete ? "Search codebase" : "Searching codebase..."
    }
  default:
    return `${functionCall?.function_name}(${Object.entries(functionCall?.function_parameters!).map(([key, value]) => `${key}="${value}"`).join(", ")})`
}
}

const roleToColor = {
  "user": "bg-zinc-600",
  "assistant": "bg-zinc-700",
  "function": "bg-zinc-800",
}

const sum = (arr: number[]) => arr.reduce((acc, cur) => acc + cur, 0)

const renderPRDiffs = (pr: PullRequest) => {
  return pr.file_diffs.map((diff, index) => (
    `@@ ${diff.filename} @@\n${diff.patch}`
  )).join("\n\n")
}

const UserMessageDisplay = ({ message, onEdit }: { message: Message, onEdit: (content: string) => void }) => {
  // TODO: finish this implementation
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState(message.content);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleClick = () => {
    setIsEditing(true);
  };

  const handleBlur = () => {
    setIsEditing(false);
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [editedContent]);


  return (
    <>
      <div className="flex justify-end">
        <FaPencilAlt className="inline-block mr-2 mt-3 hover:cursor-pointer" onClick={handleClick} />&nbsp;
        <div className="bg-zinc-800 transition-color text-sm p-3 rounded-xl mb-4 inline-block max-w-[80%] hover:bg-zinc-700 hover:cursor-pointer text-right" onClick={handleClick}>
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
              <Button onClick={(e) => {
                handleBlur()
                e.stopPropagation()
                e.preventDefault()
              }} variant="secondary" className="bg-zinc-800 text-white">
                Cancel
              </Button>
              <Button onClick={(e) => {
                onEdit(editedContent)
                setIsEditing(false)
                handleBlur()
                e.stopPropagation()
                e.preventDefault()
              }} variant="default" className="ml-2 bg-slate-600 text-white hover:bg-slate-700">
                Generate
              </Button>
            </>
          )}
        </div>
      </div>
      {!isEditing && message.annotations?.pulls?.map((pr) => (
        <div className="flex justify-end text-sm" key={pr.number}>
          <HoverCard openDelay={300} closeDelay={200}>
            <HoverCardTrigger>
              <div className="bg-zinc-800 rounded-xl p-4 mb-2 text-left hover:bg-zinc-700 hover:cursor-pointer max-w-[600px]" onClick={() => {
                window.open(`https://github.com/${pr.repo_name}/pull/${pr.number}`, "_blank")
              }}>
                <div className={`border-l-4 ${pr.status === "open" ? "border-green-500" : pr.status === "merged" ? "border-purple-500" : "border-red-500"} pl-4`}>
                  <div className="mb-2 font-bold text-md">
                    #{pr.number} {pr.title} 
                  </div>
                  <div className="mb-4 text-sm">
                    {pr.body}
                  </div>
                  <div className="text-xs text-zinc-300">
                    <div className="mb-1">{pr.repo_name}</div>
                    {pr.file_diffs.length} files changed <span className="text-green-500">+{sum(pr.file_diffs.map(diff => diff.additions))}</span> <span className="text-red-500">-{sum(pr.file_diffs.map(diff => diff.deletions))}</span>
                  </div>
                </div>
              </div>
            </HoverCardTrigger>
            <HoverCardContent className="w-[800px] max-h-[600px] overflow-y-auto">
              <div className="p-4">
                <h2 className="text-sm font-semibold mb-2">
                  Files changed
                </h2>
                <div className="text-sm text-gray-300">
                  <ol>
                    {pr.file_diffs.map((file, index) => (
                      <li key={index} className="mb-1">
                        {file.filename} <span className={`${file.status === 'added' ? 'text-green-500' : file.status === 'removed' ? 'text-red-500' : 'text-gray-400'}`}>
                          {file.status === 'added' ? <span className="text-green-500">Added (+{file.additions})</span> : file.status === 'removed' ? <span className="text-red-500">Deleted ({file.deletions})</span> : <><span className="text-green-500">+{file.additions}</span> <span className="text-red-500">-{file.deletions}</span></>}
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
            </HoverCardContent>
          </HoverCard>
        </div>
      ))}
    </>
    );
}

const MessageDisplay = ({ message, className, onEdit }: { message: Message, className?: string, onEdit: (content: string) => void }) => {
  if (message.role === "user") {
    return <UserMessageDisplay message={message} onEdit={onEdit} />
  }
  return (
    <div className={`flex justify-start`}>
      <div
        className={`transition-color text-sm p-3 rounded-xl mb-4 inline-block max-w-[80%] text-left w-[80%]
          ${message.role === "assistant" ? "py-1" : ""} ${className || roleToColor[message.role]}`}
      >
        {message.role === "function" ? (
          <Accordion type="single" collapsible className="w-full" defaultValue={((message.content && message.function_call?.function_name === "search_codebase") || (message.function_call?.snippets?.length !== undefined && message.function_call?.snippets?.length > 0)) ? "function" : undefined}>
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
                  <span>{getFunctionCallHeaderString(message.function_call)}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className={`pb-0 ${message.content && message.function_call?.function_name === "search_codebase" && !message.function_call?.is_complete ? "pt-6" : "pt-0"}`}>
                {message.function_call?.function_name === "search_codebase" && message.content && !message.function_call.is_complete && (
                  <span className="p-4 pl-2">
                    {message.content}
                  </span>
                )}
                {message.function_call!.snippets ? (
                  <div className="pb-0 pt-4">
                    {message.function_call!.snippets.map((snippet, index) => (
                      <SnippetBadge
                        key={index}
                        snippet={snippet}
                      />
                    ))}
                  </div>
                ) : (message.function_call!.function_name === "self_critique" || message.function_call!.function_name === "analysis" ? (
                  <MarkdownRenderer content={message.content} className="reactMarkdown mt-4 mb-0 py-2" />
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
                )
                )}
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        ) : message.role === "assistant" ? (
          <MarkdownRenderer content={message.content} className="reactMarkdown mb-0 py-2" />
        ) : (
          <UserMessageDisplay message={message} onEdit={onEdit} />
        )}
      </div>
    </div>
  );
};

function getJSONPrefix(buffer: string): [any[], number] {
  let stack: string[] = [];
  const matchingBrackets: Record<string, string> = {
    '[': ']',
    '{': '}',
    '(': ')'
  };
  var currentIndex = 0;
  const results = [];
  let inString = false;
  let escapeNext = false;

  for (let i = 0; i < buffer.length; i++) {
    const char = buffer[i];

    if (escapeNext) {
      escapeNext = false;
      continue;
    }

    if (char === '\\') {
      escapeNext = true;
      continue;
    }

    if (char === '"') {
      inString = !inString;
    }

    if (!inString) {
      if (matchingBrackets[char]) {
        stack.push(char);
      } else if (matchingBrackets[stack[stack.length - 1]] === char) {
        stack.pop();
        if (stack.length === 0) {
          try {
            results.push(JSON.parse(buffer.slice(currentIndex, i + 1)));
            currentIndex = i + 1;
          } catch (e) {
            continue;
          }
        }
      }
    }
  }
  // if (currentIndex == 0) {
  //   console.log(buffer); // TODO: optimize later
  // }
  return [results, currentIndex];
}

async function* streamMessages(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  isStream: React.MutableRefObject<boolean>,
  timeout: number = 90000
): AsyncGenerator<any, void, unknown> {
  let done = false;
  let buffer = "";
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  while (!done && isStream.current) {
    try {
      const { value, done: streamDone } = await Promise.race([
        reader.read(),
        new Promise<ReadableStreamDefaultReadResult<Uint8Array>>((_, reject) => {
          if (timeoutId) {
            clearTimeout(timeoutId)
          }
          timeoutId = setTimeout(() => reject(new Error("Stream timeout after " + timeout / 1000 + " seconds, this is likely caused by the LLM freezing. You can try again by editing your last message. Further, decreasing the number of snippets to retrieve in the settings will help mitigate this issue.")), timeout)
        })
      ]);

      if (streamDone) {
        done = true;
        continue;
      }
      
      if (value) {
        const decodedValue = new TextDecoder().decode(value);
        buffer += decodedValue;

        const [parsedObjects, currentIndex] = getJSONPrefix(buffer)
        for (let parsedObject of parsedObjects) {
          yield parsedObject
        }
        buffer = buffer.slice(currentIndex)
      }
    } catch (error) {
      console.error("Error during streaming:", error);
      throw error;
    } finally {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }
  if (buffer) {
    console.warn("Buffer:", buffer)
  }
}

const parsePullRequests = async (repoName: string, message: string, octokit: Octokit): Promise<PullRequest[]> => {
  const [orgName, repo] = repoName.split("/")
  const pulls = []

  try {
    const prURLs = message.match(new RegExp(`https?:\/\/github.com\/${repoName}\/pull\/(?<prNumber>[0-9]+)`, 'gm'));
    for (const prURL of prURLs || []) {
      const prNumber = prURL.split("/").pop()
      const pr = await octokit!.rest.pulls.get({
        owner: orgName,
        repo: repo,
        pull_number: parseInt(prNumber!)
      })
      const title = pr.data.title
      const body = pr.data.body
      const labels = pr.data.labels.map((label) => label.name)
      const status = pr.data.state === "open" ? "open" : pr.data.merged ? "merged" : "closed"
      const file_diffs = (await octokit!.rest.pulls.listFiles({
        owner: orgName,
        repo: repo,
        pull_number: parseInt(prNumber!)
      })).data.sort((a, b) => {
        const statusOrder: Record<string, number> = { 
          'renamed': 0,
          'copied': 1,
          'added': 2, 
          'modified': 3, 
          'changed': 4,
          'deleted': 5,
          'unchanged': 6
        };
        if (statusOrder[a.status] !== statusOrder[b.status]) {
          return statusOrder[a.status] - statusOrder[b.status];
        }
        return b.changes - a.changes;
      })
      // console.log(file_diffs)
      pulls.push({
        number: parseInt(prNumber!),
        repo_name: repoName,
        title,
        body,
        labels,
        status,
        file_diffs
      } as PullRequest)
    }

    return pulls
  } catch (e: any) {
    toast({
      title: "Failed to retrieve pull request",
      description: `The following error has occurred: ${e.message}. Sometimes, logging out and logging back in can resolve this issue.`,
      variant: "destructive"
    });
    return []
  } 
}

function App({
  defaultMessageId = ""
}: {
  defaultMessageId?: string
}) {
  const [repoName, setRepoName] = useState<string>("")
  const [repoNameValid, setRepoNameValid] = useState<boolean>(false)

  const [repoNameDisabled, setRepoNameDisabled] = useState<boolean>(false)

  const [k, setK] = useLocalStorage<number>("k", DEFAULT_K)
  const [model, setModel] = useLocalStorage<keyof typeof modelMap>("model", "claude-3-opus-20240229")
  const [snippets, setSnippets] = useState<Snippet[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [currentMessage, setCurrentMessage] = useState<string>("")
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const isStream = useRef<boolean>(false)
  const [showSurvey, setShowSurvey] = useState<boolean>(false)

  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const { data: session } = useSession()

  const posthog = usePostHog();
  const [octokit, setOctokit] = useState<Octokit | null>(null)
  const [repos, setRepos] = useState<Repository[]>([])

  const [messagesId, setMessagesId] = useState<string>(defaultMessageId)

  useEffect(() => {
    console.log(defaultMessageId)
    if (defaultMessageId) {
      (async () => {
        const response = await fetch(`/backend/messages/load/${defaultMessageId}`, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            // @ts-ignore
            "Authorization": `Bearer ${session?.user.accessToken}`
          }
        })
        const data = await response.json()
        if (data.status == "success") {
          const { repo_name, messages, snippets } = data.data
          console.log(repo_name, messages, snippets)
          setRepoName(repo_name)
          setRepoNameValid(true)
          setMessages(messages)
          setSnippets(snippets)
        } else {
          toast({
            title: "Failed to load message",
            description: `The following error has occurred: ${data.error}. Sometimes, logging out and logging back in can resolve this issue.`,
            variant: "destructive"
          });
        }
      })()
    }
  }, [defaultMessageId])

  useEffect(() => {
    if (messagesContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
      if (scrollHeight - scrollTop - clientHeight < 50) {
        messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
      }
    }
  }, [messages]);

  useEffect(() => {
    if (session) {
      const octokit = new Octokit({auth: session.user!.accessToken})
      setOctokit(octokit);
      (async () => {
        const maxPages = 5;
        let allRepositories: Repository[] = [];
        let page = 1;
        let response;
        do {
          response = await octokit.rest.repos.listForAuthenticatedUser({
            visibility: "all",
            sort: "pushed",
            per_page: 100,
            page: page,
          });
          allRepositories = allRepositories.concat(response.data);
          setRepos(allRepositories)
          page++;
        } while (response.data.length !== 0 && page < maxPages);
      })()
    }
  }, [session?.user!.accessToken])

  if (session) {
    posthog.identify(
      session.user!.email!,
      {
        email: session.user!.email,
        name: session.user!.name,
        image: session.user!.image,
      }
    );
  } else {
    return (
      <main className="flex h-screen items-center justify-center p-12">
        <Toaster />
        <Button onClick={() => signIn("github")} variant="secondary">
          <FaGithub
            className="inline-block mr-2"
            style={{ marginTop: -2 }}
          />
          Sign in with GitHub
        </Button>
      </main>
    )
  }

  const lastAssistantMessageIndex = messages.findLastIndex((message) => message.role === "assistant" && message.content.trim().length > 0)

  const save = async (
    currentRepoName: string,
    currentMessages: Message[],
    currentSnippets: Snippet[],
  ) => {
    const saveResponse = await fetch("/backend/messages/save", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // @ts-ignore
        "Authorization": `Bearer ${session?.user.accessToken}`
      },
      body: JSON.stringify(
        messagesId ?
        {repo_name: currentRepoName || repoName, messages: currentMessages || messages, snippets: currentSnippets || snippets, message_id: messagesId}
        :
        {repo_name: currentRepoName || repoName, messages: currentMessages || messages, snippets: currentSnippets || snippets}
      )
    })
    const { message_id } = await saveResponse.json()
    if (!messagesId) {
      setMessagesId(message_id)
      const updatedUrl = `/c/${message_id}`;
      window.history.pushState({}, '', updatedUrl);
    }
    console.log("saved")
  }

  const startStream = async (
    message: string,
    newMessages: Message[],
    snippets: Snippet[],
    annotations: { pulls: PullRequest[] } = { pulls: [] }
  ) => {
    setIsLoading(true);
    isStream.current = true;

    var currentSnippets = snippets;
    if (currentSnippets.length == 0) {
      try {
        const snippetsResponse = await fetch(`/backend/search`, {
          method: 'POST',
          headers: {
            "Content-Type": "application/json",
            // @ts-ignore
            "Authorization": `Bearer ${session?.user.accessToken}`
          },
          body: JSON.stringify({
            repo_name: repoName,
            query: message,
            annotations: annotations
          })
        });

        let streamedMessages: Message[] = [...newMessages]
        let streamedMessage: string = ""
        const reader = snippetsResponse.body?.getReader()!;
        for await (const chunk of streamMessages(reader, isStream)) {
          streamedMessage = chunk[0]
          currentSnippets = chunk[1]
          currentSnippets = currentSnippets.slice(0, k)
          streamedMessages = [...newMessages, {
            content: streamedMessage,
            role: "function",
            function_call: {
              function_name: "search_codebase",
              function_parameters: {},
              snippets: currentSnippets,
              is_complete: false
            }
          } as Message]
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
              function_name: "search_codebase",
              function_parameters: {},
              snippets: currentSnippets,
              is_complete: true
            }
          }
        ]
        setMessages(streamedMessages)
        if (!currentSnippets.length) {
          throw new Error("No snippets found")
        }
      } catch (e: any) {
        console.log(e)
        toast({
          title: "Failed to search codebase",
          description: `The following error has occurred: ${e.message}. Sometimes, logging out and logging back in can resolve this issue.`,
          variant: "destructive",
          duration: Infinity
        });
        setIsLoading(false);
        isStream.current = false;
        posthog.capture("chat errored", {
          repoName,
          snippets,
          newMessages,
          message,
          error: e.message
        });
        throw e;
      }
    }

    save(
      repoName,
      newMessages,
      currentSnippets
    );

    const chatResponse = await fetch("/backend/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // @ts-ignore
        "Authorization": `Bearer ${session?.user.accessToken}`
      },
      body: JSON.stringify({
        repo_name: repoName,
        messages: newMessages,
        snippets: currentSnippets,
        model: model,
        use_patch: true,
        k: k
      })
    });

    // Stream
    const reader = chatResponse.body?.getReader()!;
    var streamedMessages: Message[] = []
    var respondedMessages: Message[] = [...newMessages, { content: "", role: "assistant" } as Message]
    setMessages(respondedMessages);
    try {
      for await (const patch of streamMessages(reader, isStream)) {
        streamedMessages = jsonpatch.applyPatch(streamedMessages, patch).newDocument
        setMessages([...newMessages, ...streamedMessages])
      }
      if (!isStream.current) {
        reader!.cancel()
        posthog.capture("chat stopped", {
          repoName,
          snippets,
          newMessages,
          message,
        });
      }
    } catch (e: any) {
      toast({
        title: "Chat stream failed",
        description: e.message,
        variant: "destructive",
        duration: Infinity
      });
      setIsLoading(false);
      posthog.capture("chat errored", {
        repoName,
        snippets,
        newMessages,
        message,
        error: e.message
      });
      throw e;
    }

    isStream.current = false;

    var lastMessage = streamedMessages[streamedMessages.length - 1]
    if (lastMessage.role == "function" && lastMessage.function_call?.is_complete == false) {
      lastMessage.function_call.is_complete = true;
      setMessages([
        ...newMessages,
        ...streamedMessages.slice(0, streamedMessages.length - 1),
        lastMessage
      ])
    }

    save(
      repoName,
      [
        ...newMessages,
        ...streamedMessages.slice(0, streamedMessages.length - 1),
        lastMessage
      ],
      currentSnippets
    );

    const surveyID = process.env.NEXT_PUBLIC_SURVEY_ID
    if (surveyID && !localStorage.getItem(`hasInteractedWithSurvey_${surveyID}`)) {
      setShowSurvey(true);
    }
    setIsLoading(false);
    posthog.capture("chat succeeded", {
      repoName,
      snippets,
      newMessages,
      message,
    });
  }

  return (
    <main className="flex h-screen flex-col items-center justify-between p-12">
      <Toaster />
      {showSurvey && process.env.NEXT_PUBLIC_SURVEY_ID && (
        <Survey
          onClose={(didSubmit) => {
            setShowSurvey(false)
            if (didSubmit) {
              toast({
                title: "Thanks for your feedback!",
                description: "We'll reach back out shortly.",
              })
            }
          }}
        />
      )}
      <div className="flex justify-between w-full px-2 items-middle">
        <h1 className="text-4xl font-bold mb-6">Sweep Search</h1>
        <div className="flex items-center mb-4">
          <img
            className="rounded-full w-10 h-10 mr-4"
            src={session!.user!.image || ""}
            alt={session!.user!.name || ""}
          />
          <div>
            <p className="text-lg font-bold">{session!.user!.username! || session!.user!.name}</p>
            <p className="text-sm text-gray-400">{session!.user!.email}</p>
          </div>
          <Button className="ml-4" variant="secondary" onClick={() => signOut()}>
            Sign Out
          </Button>
        </div>
      </div>
      <div className={`mb-4 w-full flex items-center ${repoNameValid ? "" : "grow"}`}>
        <AutoComplete
          options={repos.map((repo) => ({label: repo.full_name, value: repo.full_name}))}
          placeholder="Repository name"
          emptyMessage="No repositories found"
          value={{label: repoName, value: repoName}}
          onValueChange={(option) => setRepoName(option.value)}
          disabled={repoNameDisabled}
          onBlur={async (repoName: string) => {
            console.log(repoName)
            const cleanedRepoName = repoName.replace(/\s/g, '') // might be unsafe but we'll handle it once we get there
            console.log(repoName)
            setRepoName(cleanedRepoName)
            if (cleanedRepoName === "") {
              setRepoNameValid(false)
              return;
            }
            if (!cleanedRepoName.includes("/")) {
              setRepoNameValid(false)
              toast({
                title: "Invalid repository name",
                description: "Please enter a valid repository name in the format 'owner/repo'",
                variant: "destructive",
                duration: Infinity
              })
              return;
            }
            var data = null
            try {
              setRepoNameDisabled(true);
              const response = await fetch(`/backend/repo?repo_name=${cleanedRepoName}`, {
                headers: {
                  "Content-Type": "application/json",
                  // @ts-ignore
                  "Authorization": `Bearer ${session?.user.accessToken!}`
                }
              });
              data = await response.json();
            } catch (e: any) {
              setRepoNameValid(false)
              toast({
                title: "Failed to load repository",
                description: e.message,
                variant: "destructive",
                duration: Infinity
              })
              setRepoNameDisabled(false);
              return;
            }
            if (!data.success) {
              setRepoNameValid(false)
              toast({
                title: "Failed to load repository",
                description: data.error,
                variant: "destructive",
                duration: Infinity
              })
            } else {
              setRepoNameValid(true)
              toast({
                title: "Successfully loaded repository",
                variant: "default",
              })
            }
            setRepoNameDisabled(false);
          }}
        />
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline" className="ml-4">
              <FaCog className="mr-2"/>
              Settings
            </Button>
          </DialogTrigger>
          <DialogContent className="w-120 p-16">
            <h2 className="text-2xl font-bold mb-4 text-center">
              Settings
            </h2>
            <Label>
              Model
            </Label>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="text-left">{modelMap[model]}</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56">
                <DropdownMenuLabel>Anthropic</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuRadioGroup value={model} onValueChange={(value) => setModel(value as keyof typeof modelMap)}>
                  {Object.keys(modelMap).map((model) => (
                    model.includes("claude") ? (<DropdownMenuRadioItem value={model} key={model}>{modelMap[model]}</DropdownMenuRadioItem>) : null
                  ))}
                </DropdownMenuRadioGroup>
                <DropdownMenuLabel>OpenAI</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuRadioGroup value={model} onValueChange={(value) => setModel(value as keyof typeof modelMap)}>
                  {Object.keys(modelMap).map((model) => (
                    model.includes("gpt") ? (<DropdownMenuRadioItem value={model} key={model}>{modelMap[model]}</DropdownMenuRadioItem>) : null
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
            <Label className="mt-4">
              Number of snippets
            </Label>
            <div className="flex items-center">
              <span className="mr-4 whitespace-nowrap">{k}</span>
              <Slider defaultValue={[DEFAULT_K]} max={20} min={1} step={1} onValueChange={(value) => setK(value[0])} value={[k]} className="w-[300px] my-0 py-0" />
            </div>
          </DialogContent>
        </Dialog>
      </div>
      <div
        ref={messagesContainerRef}
        className="w-full border flex-grow mb-4 p-4 max-h-[90%] overflow-y-auto rounded-xl"
        hidden={!repoNameValid}
      >
        {messages.map((message, index) => (
          <MessageDisplay
            key={index}
            message={message}
            className={index == lastAssistantMessageIndex ? "bg-slate-700" : ""}
            onEdit={async (content) => {
              const pulls = await parsePullRequests(repoName, content, octokit!)

              const newMessages: Message[] = [
                ...messages.slice(0, index),
                { ...message, content, annotations: { pulls } },
              ]
              setMessages(newMessages)
              if (index == 0) {
                setSnippets([]) 
                startStream(content, newMessages, [], { pulls })
              } else {
                startStream(content, newMessages, snippets, { pulls })
              }
            }}
          />
        ))}
        {isLoading && (
          <div className="flex justify-around w-full py-2">
            <PulsingLoader size={1.5} />
          </div>
        )}
      </div>
      {repoNameValid && (
        <div className={`flex w-full`}>
          {isStream.current ? (
            <Button
              className="mr-2"
              variant="destructive"
              onClick={async () => {
                setIsLoading(false);
                isStream.current = false;
              }}
            >
              <FaStop />&nbsp;&nbsp;Stop
            </Button>
          ) : (
            <Button
              className="mr-2"
              variant="secondary"
              onClick={async () => {
                setMessages([]);
                setCurrentMessage("");
                setIsLoading(false);
                setSnippets([]);
                setMessagesId("");
                window.history.pushState({}, '', '/');
              }}
              disabled={isLoading}
            >
              <FaArrowsRotate />&nbsp;&nbsp;Reset
            </Button>
          )}
          <Input
            data-ph-capture-attribute-current-message={currentMessage}
            onKeyUp={async (e) => {
              if (e.key === "Enter") {
                posthog.capture("chat submitted", {
                  repoName,
                  snippets,
                  messages,
                  currentMessage,
                });
                const pulls = await parsePullRequests(repoName, currentMessage, octokit!)
                const newMessages: Message[] = [...messages, { content: currentMessage, role: "user", annotations: { pulls } }];
                setMessages(newMessages);
                setCurrentMessage("");
                startStream(currentMessage, newMessages, snippets, { pulls })
              }
            }}
            onChange={(e) => setCurrentMessage(e.target.value)}
            className="p-4"
            value={currentMessage}
            placeholder="Type a message..."
            disabled={isLoading}
          />
          <Dialog>
            <DialogTrigger asChild>
              <Button
                className="ml-2"
                variant="secondary"
                onClick={async () => {
                }}
                disabled={isLoading}
              >
                <FaShareAlt />&nbsp;&nbsp;Share
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
                value={`${window.location.origin}/c/${messagesId}`}
                onClick={() => {
                  navigator.clipboard.writeText(`${window.location.origin}/c/${messagesId}`)
                  toast({
                    title: "Link copied",
                    description: "The link to your current session has been copied to your clipboard.",
                  })
                }}
                disabled
              />
              <Button className="mt-2" variant="secondary" onClick={() => {
                navigator.clipboard.writeText(`${window.location.origin}/c/${messagesId}`)
                toast({
                  title: "Link copied",
                  description: "The link to your current session has been copied to your clipboard.",
                })
              }}>
                Copy
              </Button>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </main>
  );
}

export default function WrappedApp({
  session,
  ...props
}: {
  session: Session | null;
  [key: string]: any;
}) {
  return (
    <PostHogProvider>
      <SessionProvider session={session}>
        <App {...props} />
      </SessionProvider>
    </PostHogProvider>
  )
}
