"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "../components/ui/input"
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { tomorrow } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { FaCheck, FaGithub } from "react-icons/fa";
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

if (typeof window !== 'undefined') {
  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_KEY!)
  posthog.debug(false)
}

interface Snippet {
  content: string;
  start: number;
  end: number;
  file_path: string;
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

const sliceLines = (content: string, start: number, end: number) => {
  return content.split("\n").slice(Math.max(start - 1, 0), end).join("\n");
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
    <div className={`p-2 rounded-xl mb-2 text-xs inline-block mr-2 bg-zinc-800 ${className || ""}`}>
      <HoverCard openDelay={300} closeDelay={200}>
        <HoverCardTrigger asChild>
          <Button variant="link" className="text-sm py-0 px-1 h-6 leading-4">
            <span>
              {snippet.end > snippet.content.split('\n').length - 3 && snippet.start == 0 ?
                snippet.file_path : `${snippet.file_path}:${snippet.start}-${snippet.end}`
              }
            </span>
          </Button>
        </HoverCardTrigger>
        <HoverCardContent className="w-[500px] mr-2">
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
    case "self_critique":
      return functionCall.is_complete ? "Self critique" : "Self critiquing..."
    case "search_codebase":
      if (functionCall!.function_parameters?.query) {
        return functionCall.is_complete ? `Search codebase for "${functionCall.function_parameters.query}"` : `Searching codebase for "${functionCall.function_parameters.query}"...`
      } else {
        return functionCall.is_complete ? "Search codebase" : "Searching codebase..."
      }
    default:
      return `${functionCall?.function_name}(${Object.entries(functionCall?.function_parameters!).map(([key, value]) => `${key}="${value}"`).join(", ")})`
  }
}

const MessageDisplay = ({ message }: { message: Message }) => {
  return (
    <div className={`flex ${message.role !== "user" ? "justify-start" : "justify-end"}`}>
      <div
        className={`text-sm p-3 rounded-xl mb-4 inline-block max-w-[80%] ${message.role !== "user" ? "text-left bg-zinc-700 w-[80%]" : "text-right bg-zinc-800"
          }`}
      >
        {message.role === "function" ? (
          <Accordion type="single" collapsible className="w-full" defaultValue={Boolean(message.function_call?.snippets?.length) ? "function" : undefined}>
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
              <AccordionContent className="pb-0">
                {message.function_call!.snippets ? (
                  <div className="pb-0 pt-4">
                    {message.function_call!.snippets.map((snippet, index) => (
                      <SnippetBadge
                        key={index}
                        snippet={snippet}
                      />
                    ))}
                  </div>
                ) : (message.function_call!.function_name === "self_critique" ? (
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
        ) : (
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
        )}
      </div>
    </div>
  );
};


const getLastLine = (content: string) => {
  const splitContent = content.trim().split("\n");
  return splitContent[splitContent.length - 1];
}

const defaultMessage = `I'm Sweep and I'm here to help you answer questions about your codebase!`;

function App() {
  const [repoName, setRepoName] = useLocalStorage<string>("repoName", "")
  const [repoNameValid, setRepoNameValid] = useLocalStorage<boolean>("repoNameValid", false)

  const [repoNameDisabled, setRepoNameDisabled] = useState<boolean>(false)

  const [snippets, setSnippets] = useLocalStorage<Snippet[]>("snippets", [])
  const [messages, setMessages] = useLocalStorage<Message[]>("messages", [
    { content: defaultMessage, role: "assistant" },
  ])
  const [currentMessage, setCurrentMessage] = useLocalStorage<string>("currentMessage", "")
  const [isLoading, setIsLoading] = useState<boolean>(false)
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
        <h1 className="text-4xl font-bold mb-6">Sweep Chat</h1>
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
      <div className={`w-full flex items-center ${repoNameValid ? "" : "grow"}`}>
        <Input
          data-ph-capture-attribute-repo-name={repoName}
          className="mb-4"
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
            setRepoNameDisabled(true);
            const response = await fetch(`/backend/repo?repo_name=${repoName}`, {
              headers: {
                "Content-Type": "application/json",
                // @ts-ignore
                "Authorization": `Bearer ${session?.accessToken!}`
              }
            });
            setRepoNameDisabled(false);
            console.log(response)
            const data = await response.json();
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
          }}
          placeholder="Repository name"
          disabled={repoNameDisabled}
        />
      </div>
      <div
        ref={messagesContainerRef}
        className="w-full border flex-grow mb-4 p-4 max-h-[90%] overflow-y-auto rounded-xl"
        hidden={!repoNameValid}
      >
        {messages.map((message, index) => (
          <MessageDisplay key={index} message={message} />
        ))}
        {isLoading && (
          <div className="flex justify-around w-full py-2">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-zinc-500 ml-4 mr-4"></div>
          </div>
        )}
      </div>
      {repoNameValid && (
        <div className={`flex w-full`}>
          <Button
            className="mr-2"
            variant="secondary"
            onClick={async () => {
              setMessages([{ content: defaultMessage, role: "assistant" }]);
              setCurrentMessage("");
              setIsLoading(false);
              setSnippets([]);
            }}
            disabled={isLoading}
          >
            Restart
          </Button>
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
                (async () => {
                  if (currentMessage !== "") {
                    const newMessages: Message[] = [...messages, { content: currentMessage, role: "user" }];
                    setMessages(newMessages);
                    setCurrentMessage("");
                    setIsLoading(true);

                    var currentSnippets = snippets;
                    if (currentSnippets.length == 0) {
                      try {
                        const snippetsResponse = await fetch(`/backend/search?repo_name=${repoName}&query=${encodeURIComponent(currentMessage)}`, {
                          headers: {
                            "Content-Type": "application/json",
                            // @ts-ignore
                            "Authorization": `Bearer ${session?.accessToken}`
                          }
                        });
                        currentSnippets = (await snippetsResponse.json() as Snippet[]).slice(0, 5);
                        setSnippets(currentSnippets);
                      } catch (e: any) {
                        toast({
                          title: "Failed to search codebase",
                          description: e.message,
                          variant: "destructive"
                        });
                        setIsLoading(false);
                        posthog.capture("chat errored", {
                          repoName,
                          snippets,
                          messages,
                          currentMessage,
                          error: e.message
                        });
                        throw e;
                      }
                    }
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
                      })
                    });

                    // Stream
                    const reader = chatResponse.body?.getReader();
                    let done = false;
                    let chat = "";
                    var respondedMessages: Message[] = [...newMessages, { content: "", role: "assistant" }]
                    setMessages(respondedMessages);
                    try {
                      while (!done) {
                        const { value, done: done_ } = await reader!.read();
                        if (value) {
                          const decodedValue = new TextDecoder().decode(value);
                          chat += decodedValue;
                          console.log(chat)
                          const lastLine = getLastLine(chat);
                          if (lastLine !== "") {
                            try {
                              const addedMessages = JSON.parse(lastLine);
                              respondedMessages = [...newMessages, ...addedMessages]
                              setMessages(respondedMessages);
                            } catch (e: any) { }
                            chat = lastLine
                          }
                        }
                        done = done_;
                      }
                    } catch (e: any) {
                      toast({
                        title: "Chat stream failed",
                        description: e.message,
                        variant: "destructive"
                      });
                      console.log(chat)
                      setIsLoading(false);
                      posthog.capture("chat errored", {
                        repoName,
                        snippets,
                        messages,
                        currentMessage,
                        error: e.message
                      });
                      throw e;
                    }

                    const surveyID = process.env.NEXT_PUBLIC_SURVEY_ID
                    if (surveyID && localStorage.getItem(`hasInteractedWithSurvey_${surveyID}`)) {
                      setShowSurvey(true);
                    }
                    setIsLoading(false);
                    posthog.capture("chat succeeded", {
                      repoName,
                      snippets,
                      messages,
                      currentMessage,
                    });
                  }
                })()
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
