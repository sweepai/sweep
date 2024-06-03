"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "../components/ui/input"
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { tomorrow } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { FaCheck, FaCog, FaGithub, FaPencilAlt, FaStop } from "react-icons/fa";
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


if (typeof window !== 'undefined') {
  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY!)
  posthog.debug(false)
}

interface Snippet {
  content: string;
  start: number;
  end: number;
  file_path: string;
  type_name: "source" | "tests" | "dependencies" | "tools" | "docs";
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
    <div className={`p-2 rounded-xl mb-2 text-xs inline-block mr-2 ${typeNameToColor[snippet.type_name]} ${className || ""} `}>
      <HoverCard openDelay={300} closeDelay={200}>
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
        <HoverCardContent className="w-[800px] mr-2">
          <SyntaxHighlighter
            PreTag="div"
            language="python"
            style={tomorrow}
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
      {button}
    </div>
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
      <div className={`text-sm text-white`} onClick={handleClick}>
        {isEditing ? (
          <Textarea
            className="w-full mb-4 bg-transparent text-white max-w-[500px] w-[500px] hover:bg-initial"
            ref={textareaRef}
            value={editedContent}
            onChange={(e) => setEditedContent(e.target.value)}
            autoFocus
          />
        ) : (
          <>
            <span className="bg-initial pl-1">
              <FaPencilAlt className="inline-block mr-2" />&nbsp;
              {message.content}
            </span>
          </>
        )}
      </div>
      {isEditing && (
        <>
          <Button onClick={() => handleBlur()} variant="secondary" className="bg-zinc-800 text-white">
            Cancel
          </Button>
          <Button onClick={() => {
            onEdit(editedContent)
            handleBlur()
          }} variant="default" className="ml-2 bg-slate-600 text-white hover:bg-slate-700">
            Generate
          </Button>
        </>
      )}
  </>
  );
}

const MessageDisplay = ({ message, className, onEdit }: { message: Message, className?: string, onEdit: (content: string) => void }) => {
  return (
    <div className={`flex ${message.role !== "user" ? "justify-start" : "justify-end"}`}>
      <div
        className={`transition-color text-sm p-3 rounded-xl mb-4 inline-block max-w-[80%] ${message.role !== "user" ? "text-left w-[80%]" : "hover:bg-zinc-700 hover:cursor-pointer text-right"
          } ${message.role === "assistant" ? "py-1" : ""} ${className || roleToColor[message.role]}`}
      >
        {message.role === "function" ? (
          <Accordion type="single" collapsible className="w-full" defaultValue={((message.content && message.function_call?.function_name === "search_codebase") || (message.function_call?.snippets?.length !== undefined && message.function_call?.snippets?.length > 0)) ? "function" : undefined}>
            <AccordionItem value="function" className="border-none">
              <AccordionTrigger className="border-none py-0 text-left">
                <div className="text-xs text-gray-400 flex align-center">
                  {!message.function_call!.is_complete ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-zinc-500 mr-2"></div>
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
                  <Markdown
                    className="reactMarkdown mt-4 mb-0"
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
                            style={tomorrow}
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
                    {message.content}
                  </Markdown>
                ) : (
                  <SyntaxHighlighter
                    language="xml"
                    style={tomorrow}
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
          <Markdown
            className="reactMarkdown"
            remarkPlugins={[remarkGfm]}
            components={{
              code(props) {
                const { children, className, node, ref, ...rest } = props
                const match = /language-(\w+)/.exec(className || '')
                return match ? (
                  <SyntaxHighlighter
                    {...rest}
                    PreTag="div"
                    language={match[1]}
                    style={tomorrow}
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
            {message.content}
          </Markdown>
        ) : (
          <UserMessageDisplay message={message} onEdit={onEdit} />
        )}
      </div>
    </div>
  );
};


function App() {
  const [repoName, setRepoName] = useLocalStorage<string>("repoName", "")
  const [repoNameValid, setRepoNameValid] = useLocalStorage<boolean>("repoNameValid", false)

  const [repoNameDisabled, setRepoNameDisabled] = useState<boolean>(false)

  const [k, setK] = useLocalStorage<number>("k", DEFAULT_K)
  const [model, setModel] = useLocalStorage<keyof typeof modelMap>("model", "claude-3-opus-20240229")
  const [snippets, setSnippets] = useLocalStorage<Snippet[]>("snippets", [])
  const [messages, setMessages] = useLocalStorage<Message[]>("messages", [])
  const [currentMessage, setCurrentMessage] = useLocalStorage<string>("currentMessage", "")
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const isStream = useRef<boolean>(false)
  const [showSurvey, setShowSurvey] = useState<boolean>(false)

  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const { data: session } = useSession()

  const posthog = usePostHog();

  if (session) {
    posthog.identify(
      session.user!.email!,
      {
        email: session.user!.email,
        name: session.user!.name,
      }
    );
  }

  useEffect(() => {
    if (messagesContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
      if (scrollHeight - scrollTop - clientHeight < 100) {
        messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
      }
    }
  }, [messages]);

  const lastAssistantMessageIndex = messages.findLastIndex((message) => message.role === "assistant" && message.content.trim().length > 0)

  const startStream = async (message: string, newMessages: Message[]) => {
    setIsLoading(true);
    isStream.current = true;

    var currentSnippets = snippets;
    if (currentSnippets.length == 0) {
      try {
        const snippetsResponse = await fetch(`/backend/search?repo_name=${repoName}&query=${encodeURIComponent(message)}&stream=true`, {
          headers: {
            "Content-Type": "application/json",
            // @ts-ignore
            "Authorization": `Bearer ${session?.accessToken}`
          }
        });
        const reader = snippetsResponse.body?.getReader();
        let done = false;
        let buffer = "";
        let streamedMessages: Message[] = [...newMessages]
        let currentSnippets: Snippet[] = []
        let streamedMessage: string = ""
        while (!done && isStream.current) {
          const { value, done: done_ } = await Promise.race([
            reader!.read() as Promise<ReadableStreamDefaultReadResult<Uint8Array>>,
            new Promise<ReadableStreamDefaultReadResult<Uint8Array>>((_, reject) => setTimeout(() => reject(new Error("Stream timeout after 90 seconds. You can try again by editing your last message.")), 90000))
          ]);
          console.log(value)
          if (value) {
            const decodedValue = new TextDecoder().decode(value);
            buffer += decodedValue;
            buffer = buffer.replace("][{", "]\n[{")
            var newBuffer = "";
            const bufferLines = buffer.trim().split("\n")
            try {
              for (var i = 0; i < bufferLines.length; i += 1) {
                [streamedMessage, currentSnippets] = JSON.parse(bufferLines[i])
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
                }]
                if (currentSnippets) {
                  setSnippets(currentSnippets)
                }
                setMessages(streamedMessages)
              }
            } catch (e: any) {
              continue
            }
            buffer = newBuffer
          }
          done = done_;
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
      } catch (e: any) {
        console.log(e)
        toast({
          title: "Failed to search codebase",
          description: `The following error has occurred: ${e.message}. Sometimes, logging out and logging back in can resolve this issue.`,
          variant: "destructive"
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
    }
    console.log(model)
    const chatResponse = await fetch("/backend/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // @ts-ignore
        "Authorization": `Bearer ${session?.accessToken}`
      },
      body: JSON.stringify({
        repo_name: repoName,
        messages: newMessages,
        snippets: currentSnippets,
        model: model,
        use_patch: true
      })
    });

    // Stream
    const reader = chatResponse.body?.getReader();
    let done = false;
    let buffer = "";
    var streamedMessages: Message[] = []
    var respondedMessages: Message[] = [...newMessages, { content: "", role: "assistant" }]
    setMessages(respondedMessages);
    try {
      while (!done && isStream.current) {
        const { value, done: done_ } = await Promise.race([
          reader!.read() as Promise<ReadableStreamDefaultReadResult<Uint8Array>>,
          new Promise<ReadableStreamDefaultReadResult<Uint8Array>>((_, reject) => setTimeout(() => reject(new Error("Stream timeout after 90 seconds. You can try again by editing your last message.")), 90000))
        ]);
        if (value) {
          const decodedValue = new TextDecoder().decode(value);
          buffer += decodedValue;
          buffer = buffer.replace("][{", "]\n[{")
          var newBuffer = "";
          const bufferLines = buffer.trim().split("\n")

          for (var i = 0; i < bufferLines.length; i += 1) {
            const line = bufferLines[i];
            if (line !== "") {
              try {
                const patch = JSON.parse(line)
                streamedMessages = jsonpatch.applyPatch(streamedMessages, patch).newDocument
              } catch (e: any) {
                if (i == bufferLines.length - 1) {
                  newBuffer = line
                } else {
                  console.log(e.message)
                  console.log(buffer)
                }
              }
            }
          }
          setMessages([...newMessages, ...streamedMessages])

          buffer = newBuffer
        }
        done = done_;
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
        variant: "destructive"
      });
      console.log(buffer)
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

  if (!session) {
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
            <p className="text-lg font-bold">{session!.user!.name}</p>
            <p className="text-sm text-gray-400">{session!.user!.email}</p>
          </div>
          <Button className="ml-4" variant="secondary" onClick={() => signOut()}>
            Sign Out
          </Button>
        </div>
      </div>
      <div className={`mb-4 w-full flex items-center ${repoNameValid ? "" : "grow"}`}>
        <Input
          data-ph-capture-attribute-repo-name={repoName}
          className=""
          value={repoName}
          onChange={(e) => setRepoName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.currentTarget.blur();
            }
          }}
          onBlur={async () => {
            if (repoName === "") {
              setRepoNameValid(false)
              return;
            }
            if (!repoName.includes("/")) {
              setRepoNameValid(false)
              toast({
                title: "Invalid repository name",
                description: "Please enter a valid repository name in the format 'owner/repo'",
                variant: "destructive"
              })
              return;
            }
            var data = null
            try {
              setRepoNameDisabled(true);
              const response = await fetch(`/backend/repo?repo_name=${repoName}`, {
                headers: {
                  "Content-Type": "application/json",
                  // @ts-ignore
                  "Authorization": `Bearer ${session?.accessToken!}`
                }
              });
              console.log(response)
              data = await response.json();
            } catch (e: any) {
              setRepoNameValid(false)
              toast({
                title: "Failed to load repository",
                description: e.message,
                variant: "destructive"
              })
              setRepoNameDisabled(false);
              return;
            }
            if (!data.success) {
              setRepoNameValid(false)
              toast({
                title: "Failed to load repository",
                description: data.error,
                variant: "destructive"
              })
            } else {
              setRepoNameValid(true)
              toast({
                title: "Successfully loaded repository",
                variant: "default"
              })
            }
            setRepoNameDisabled(false);
          }}
          placeholder="Repository name"
          disabled={repoNameDisabled}
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
            onEdit={(content) => {
              console.log(index)
              const newMessages = [
                ...messages.slice(0, index),
                { ...message, content },
              ]
              setMessages(newMessages)
              if (index == 0) {
                setSnippets([])
              }
              startStream(content, newMessages)
            }}
          />
        ))}
        {isLoading && (
          <div className="flex justify-around w-full py-2">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-zinc-500 ml-4 mr-4"></div>
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
              <FaStop />
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
              }}
              disabled={isLoading}
            >
              <FaArrowsRotate />
            </Button>
          )}
          <Input
            data-ph-capture-attribute-current-message={currentMessage}
            onKeyUp={(e) => {
              if (e.key === "Enter") {
                posthog.capture("chat submitted", {
                  repoName,
                  snippets,
                  messages,
                  currentMessage,
                });
                const newMessages: Message[] = [...messages, { content: currentMessage, role: "user" }];
                setMessages(newMessages);
                setCurrentMessage("");
                startStream(currentMessage, newMessages)
              }
            }}
            onChange={(e) => setCurrentMessage(e.target.value)}
            className="p-4"
            value={currentMessage}
            placeholder="Type a message..."
            disabled={isLoading}
          />
        </div>
      )}
    </main>
  );
}

export default function WrappedApp({
  session
}: {
  session: Session | null;
}) {
  return (
    <PostHogProvider>
      <SessionProvider session={session}>
        <App />
      </SessionProvider>
    </PostHogProvider>
  )
}
