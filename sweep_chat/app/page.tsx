"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "../components/ui/input"
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {Prism as SyntaxHighlighter} from 'react-syntax-highlighter'
import {tomorrow} from 'react-syntax-highlighter/dist/esm/styles/prism'
import { FaCheck, FaPlus, FaTrash } from "react-icons/fa";
import { Button } from "@/components/ui/button";
import { useLocalStorage } from "usehooks-ts";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Toaster } from "@/components/ui/toaster";
import { toast } from "@/components/ui/use-toast";

interface Message {
  content: string; // This is the message content or function output
  role: "user" | "assistant" | "function";
  function_call?: {
    function_name: string;
    function_parameters: Record<string, any>;
    is_complete: boolean;
  }; // This is the function input
}

interface Snippet {
  content: string;
  start: number;
  end: number;
  file_path: string;
}

const MessageDisplay = ({ message }: { message: Message }) => {
  return (
    <div className={`flex ${message.role !== "user" ? "justify-start" : "justify-end"}`}>
      <div
        className={`text-sm p-3 rounded-xl mb-4 inline-block max-w-[80%] ${
          message.role !== "user" ? "text-left bg-zinc-700 w-[80%]" : "text-right bg-zinc-800"
        }`}
      >
        {message.role === "function" ? (
          <Accordion type="single" collapsible className="w-full">
            <AccordionItem value="function" className="border-none">
              <AccordionTrigger className="border-none py-0 text-left">
                <div className="text-xs text-gray-400 flex align-center">
                  {!message.function_call!.is_complete ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-zinc-500 mr-2"></div>
                  ): (
                    <FaCheck
                      className="inline-block mr-2"
                      style={{ marginTop: 2}}
                    />
                  )}
                  {message.function_call!.function_name === "self_critique" ? (
                    message.function_call!.is_complete ? (
                      <span>Self critique</span>
                    ): (
                      <span>Self critiquing...</span>
                    )
                  ): (
                    <span>{message.function_call!.function_name}({Object.entries(message.function_call!.function_parameters).map(([key, value]) => `${key}="${value}"`).join(", ")})</span>
                  )}
                </div>
              </AccordionTrigger>
              <AccordionContent>
                {message.function_call!.function_name === "self_critique" ? (
                  <Markdown
                    className="reactMarkdown mt-4 mb-0"
                    remarkPlugins={[remarkGfm]}
                    components={{
                      code(props) {
                        const {children, className, node, ref, ...rest} = props
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
                const {children, className, node, ref, ...rest} = props
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
  button: JSX.Element;
}) => {
  return (
    <div className={`p-2 rounded-xl mb-4 text-xs inline-block mr-2 bg-zinc-800 ${className || ""}`}>
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
        <HoverCardContent className="w-100 mr-2">
          <SyntaxHighlighter
            PreTag="div"
            language="python"
            style={tomorrow}
            customStyle={{
              backgroundColor: 'transparent',
              whiteSpace: 'pre-wrap',
            }}
            className="rounded-xl max-h-80 overflow-y-auto p-4"
          >
            {sliceLines(snippet.content, snippet.start, snippet.end)}
          </SyntaxHighlighter>
        </HoverCardContent>
      </HoverCard>
      {button}
    </div>
  )
}

const getLastLine = (content: string) => {
  const splitContent = content.trim().split("\n");
  return splitContent[splitContent.length - 1];
}

const defaultMessage = `I'm Sweep and I'm here to help you answer questions about your codebase!`;

export default function Home() {
  const [repoName, setRepoName] = useLocalStorage<string>("repoName", "")
  const [repoNameDisabled, setRepoNameDisabled] = useState<boolean>(false)

  const [relevantSnippets, setRelevantSnippets] = useLocalStorage<Snippet[]>("relevantSnippets", [])
  const [suggestedSnippets, setSuggestedSnippets] = useLocalStorage<Snippet[]>("suggestedSnippets", [])
  const [showSuggestions, setShowSuggestions] = useState<boolean>(false)
  const [messages, setMessages] = useLocalStorage<Message[]>("messages", [
    { content: defaultMessage, role: "assistant" },
  ])
  const [currentMessage, setCurrentMessage] = useLocalStorage<string>("currentMessage", "")
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (messagesContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
      if (scrollHeight - scrollTop - clientHeight < 100) {
        messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
      }
    }
  }, [messages]);
  return (
    <main className="flex h-screen flex-col items-center justify-between p-12">
      <Toaster />
      <h1 className="text-4xl font-bold mb-6">Sweep Chat</h1>
      <Input
        className="mb-4"
        value={repoName}
        onChange={(e) => setRepoName(e.target.value)}
        onBlur={async () => {
          setRepoNameDisabled(true);
          const response = await fetch(`/api/repo?repo_name=${repoName}`);
          setRepoNameDisabled(false);
          console.log(response)
          const data = await response.json();
          if (!data.success) {
            toast({
              title: "Failed to load repository",
              description: data.error,
              variant: "destructive"
            })
          } else {
            toast({
              title: "Successfully loaded repository",
              variant: "default"
            })
          }
        }}
        placeholder="Repository name"
        disabled={repoNameDisabled}
      />
      <div
        ref={messagesContainerRef}
        className="w-full border flex-grow mb-4 p-4 max-h-[90%] overflow-y-auto rounded-xl"
      >
        {messages.map((message, index) => (
          <MessageDisplay key={index} message={message} />
        ))}
      </div>
      {relevantSnippets.length > 0 && (
        <div className="w-full border p-4 mb-4 rounded-xl">
          <h2 className="text-xl font-bold mb-4 flex">
            <div>
              Relevant code
            </div>
            <div className="grow"/>
            <div className="text-md flex items-center space-x-2">
              <Label htmlFor="show-suggested">Show suggested</Label>
              <Switch
                id="show-suggested"
                className="text-sm"
                checked={showSuggestions}
                onClick={() => setShowSuggestions(showSuggestions => !showSuggestions)}
              />
            </div>
          </h2>
          {relevantSnippets.map((snippet, index) => (
            <SnippetBadge
              key={index}
              snippet={snippet}
              button={
                <Button
                  className="p-0 ml-2 bg-transparent text-white hover:bg-transparent hover:drop-shadow h-fit"
                  size="sm"
                  onClick={() => {
                    setRelevantSnippets(relevantSnippets.filter((_, i) => i !== index));
                    // setSuggestedSnippets([...suggestedSnippets, snippet])
                  }}
                >
                  <FaTrash
                    className="inline-block"
                    style={{ marginTop: -5 }}
                  />
                </Button>
              }
            />
          ))}
          {showSuggestions && suggestedSnippets.map((snippet, index) => (
              <SnippetBadge
                key={index}
                snippet={snippet}
                className="bg-zinc-900"
                button={
                  <Button
                    className="p-0 ml-2 bg-transparent text-white hover:bg-transparent hover:drop-shadow h-fit"
                    size="sm"
                    onClick={() => {
                      setRelevantSnippets([...relevantSnippets, snippet]);
                      setSuggestedSnippets(suggestedSnippets.filter((_, i) => i !== index));
                    }}
                  >
                    <FaPlus
                      className="inline-block"
                      style={{ marginTop: -5 }}
                    />
                  </Button>
                }
              />
            ))
          }
        </div>
      )}
      <div className="flex w-full">
        {isLoading ? (
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-zinc-500 ml-4 mr-4"></div>
        ) : (
          <Button
            className="mr-2"
            variant="secondary"
            onClick={async () => {
              setMessages([{ content: defaultMessage, role: "assistant" }]);
              setCurrentMessage("");
              setRelevantSnippets([]);
              setSuggestedSnippets([]);
            }}
          >
            Restart
          </Button>
        )}
        <Input 
          onKeyUp={(e) => {
            if (e.key === "Enter") {
              (async () => {
                if (currentMessage !== "") {
                  const newMessages: Message[] = [...messages, { content: currentMessage, role: "user" }];
                  setMessages(newMessages);
                  setCurrentMessage("");
                  setIsLoading(true);

                  var currentRelevantSnippets = relevantSnippets;
                  if (relevantSnippets.length == 0) {
                    try {
                      const snippetsResponse = await fetch(`/api/search?repo_name=${repoName}&query=${encodeURIComponent(currentMessage)}`);
                      const snippets = await snippetsResponse.json();
                      setRelevantSnippets(snippets.slice(0, 5));
                      setSuggestedSnippets(snippets.slice(5));
                      currentRelevantSnippets = snippets;
                    } catch (e) {
                      setIsLoading(false);
                      toast({
                        title: "Failed to search for snippets",
                        description: e.message,
                        variant: "destructive"
                      });
                      return;
                    }
                  }

                  const chatResponse = await fetch("/api/chat", {
                    method: "POST",
                    headers: {
                      "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                      repo_name: repoName,
                      messages: newMessages,
                      snippets: currentRelevantSnippets.slice(0, 5),
                    })
                  });

                  try {
                    // Stream
                    const reader = chatResponse.body?.getReader();
                    let done = false;
                    let chat = "";
                    var respondedMessages: Message[] = [...newMessages, { content: "", role: "assistant" }]
                    setMessages(respondedMessages);
                    while (!done) {
                      const { value, done: done_ } = await reader.read();
                      if (value) {
                        const decodedValue = new TextDecoder().decode(value);
                        chat += decodedValue;
                        const lastLine = getLastLine(chat);
                        if (lastLine !== "") {
                          try {
                            const addedMessages = JSON.parse(lastLine);
                            respondedMessages = [...newMessages, ...addedMessages]
                            setMessages(respondedMessages);
                          } catch (e) {
                          }
                        }
                      }
                      done = done_;
                    }
                  } catch (e) {
                    toast({
                      title: "Failed to chat",
                      description: e.message,
                      variant: "destructive"
                    });
                  }

                  setIsLoading(false);
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
    </main>
  );
}
