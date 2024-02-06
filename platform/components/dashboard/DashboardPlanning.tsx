import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { ReactNode, useEffect, useRef, useState } from "react";
import CodeMirror, { EditorView, keymap, lineNumbers } from "@uiw/react-codemirror";
import { FileChangeRequest, Snippet } from "@/lib/types";
import { ScrollArea } from "../ui/scroll-area";
import { Button } from "../ui/button";
import { indentWithTab } from "@codemirror/commands";
import { indentUnit } from "@codemirror/language";
import { xml } from "@codemirror/lang-xml";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";
import { Switch } from "../ui/switch";
import { getFile } from "@/lib/api.service";
import Markdown from 'react-markdown'
import { Mention, MentionsInput, SuggestionDataItem } from "react-mentions";
import { Badge } from "../ui/badge";
import { FaTimes } from "react-icons/fa";

const systemMessagePrompt = `You are a brilliant and meticulous engineer assigned to plan code changes for the following user's concerns. Take into account the current repository's language, frameworks, and dependencies.`

const userMessagePrompt = `Here are relevant read-only files:
<read_only_files>
{readOnlyFiles}
</read_only_files>

Here is the user's request:
<user_request>
{userRequest}
</user_request>

# Task:
Analyze the snippets, repo, and user request to break down the requested change and propose a plan to addresses the user's request. Mention all changes required to solve the request.

Provide a plan to solve the issue, following these rules:
* You may only create new files and modify existing files but may not necessarily need both.
* Include the full path (e.g. src/main.py and not just main.py), using the snippets for reference.
* Use natural language instructions on what to modify regarding business logic.
* Be concrete with instructions and do not write "identify x" or "ensure y is done". Instead write "add x" or "change y to z".
* Refer to the user as "you".

You MUST follow the following format with XML tags:

# Contextual Request Analysis:
<contextual_request_analysis>
Briefly outline the minimal plan that solves the user request by referencing the snippets, and names of entities. and any other necessary files/directories.
</contextual_request_analysis>

# Plan:
<plan>
<create file="file_path_1" relevant_files="space-separated list of ALL files relevant for creating file_path_1">
* Concise natural language instructions for creating the new file needed to solve the issue.
* Reference necessary files, imports and entity names.
...
</create>
...

<modify file="file_path_2" start_line="i" end_line="j" relevant_files="space-separated list of ALL files relevant for modifying file_path_2">
* Concise natural language instructions for the modifications needed to solve the issue.
* Reference necessary files, imports and entity names.
...
</modify>
...

</plan>`

const readOnlyFileFormat = `<read_only_file file="{file}" start_line="{start_line}" end_line="{end_line}">
{contents}
</read_only_file>`;

const chainOfThoughtPattern = /<contextual_request_analysis>(?<content>[\s\S]*?)($|<\/contextual_request_analysis>)/;
const fileChangeRequestPattern = /<create file="(?<cFile>.*?)" relevant_files="(?<relevant_files>.*?)">(?<cInstructions>[\s\S]*?)($|<\/create>)|<modify file="(?<mFile>.*?)" start_line="(?<startLine>.*?)" end_line="(?<endLine>.*?)" relevant_files="(.*?)">(?<mInstructions>[\s\S]*?)($|<\/modify>)/sg;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const DashboardPlanning = ({
  repoName,
  files,
  setFileChangeRequests,
}: {
  repoName: string;
  files: {label: string; value: string}[];
  setFileChangeRequests: (fileChangeRequests: FileChangeRequest[]) => void;
}) => {
  const [instructions, setInstructions] = useLocalStorage("globalInstructions", "");
  const [snippets, setSnippets] = useLocalStorage("globalSnippets", {} as {[key: string]: Snippet});
  const [rawResponse, setRawResponse] = useLocalStorage("planningRawResponse", "");
  const [chainOfThought, setChainOfThought] = useLocalStorage("globalChainOfThought", "");
  const [currentFileChangeRequests, setCurrentFileChangeRequests] = useLocalStorage("globalFileChangeRequests", [] as FileChangeRequest[]);
  const [debugLogToggle, setDebugLogToggle] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const instructionsRef = useRef<HTMLTextAreaElement>(null);
  const thoughtsRef = useRef<HTMLDivElement>(null);
  const planRef = useRef<HTMLDivElement>(null);

  const extensions = [
    xml(),
    EditorView.lineWrapping,
    keymap.of([indentWithTab]),
    indentUnit.of("    "),
  ];

  useEffect(() => {
    if (instructionsRef.current) {
      console.log(instructionsRef.current)
      instructionsRef.current.focus();
    }
  }, [])

  const generatePlan = async () => {
    console.log("Generating plan...")
    console.log(instructions)
    setIsLoading(true)
    try {
      setChainOfThought("")
      setCurrentFileChangeRequests([])
      const response = await fetch("/api/openai/edit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          userMessage: userMessagePrompt
            .replace("{userRequest}", instructions)
            .replace(
              "{readOnlyFiles}",
              Object.keys(snippets)
                .map((filePath) =>
                  readOnlyFileFormat
                    .replace("{file}", snippets[filePath].file)
                    .replace("{start_line}", snippets[filePath].start.toString())
                    .replace("{end_line}", snippets[filePath].end.toString())
                    .replace("{contents}", snippets[filePath].content),
                )
                .join("\n"),
            ),
          systemMessagePrompt,
        }),
      })
      const reader = response.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      let rawText = "";
      while (true) {
        const { done, value } = await reader?.read()!
        if (done) {
          break;
        }
        const text = decoder.decode(value);
        rawText += text;
        setRawResponse(rawText)
        const chainOfThoughtMatch = rawText.match(chainOfThoughtPattern);
        setChainOfThought(chainOfThoughtMatch?.groups?.content || "")
        if (thoughtsRef.current) {
          thoughtsRef.current.scrollTop = thoughtsRef.current.scrollHeight || 0;
        }
        const fileChangeRequestMatches = rawText.matchAll(fileChangeRequestPattern);
        var fileChangeRequests = [];
        for (const match of fileChangeRequestMatches) {
          const file: string = match.groups?.cFile || match.groups?.mFile;
          const relevantFiles: string = match.groups?.relevant_files;
          const instructions: string = match.groups?.cInstructions || match.groups?.mInstructions || "";
          const changeType: "create" | "modify" = match.groups?.cInstructions ? "create" : "modify";
          const contents: string = (await getFile(repoName, file)).contents || "";
          const startLine: string | undefined = match.groups?.startLine;
          const start: number = startLine === undefined ? 0 : parseInt(startLine);
          const endLine: string | undefined = match.groups?.endLine;
          const end: number = endLine === undefined ? contents.split("\n").length : parseInt(endLine);
          console.log(changeType, relevantFiles, instructions, startLine, endLine)
          fileChangeRequests.push({
            snippet: {
              start,
              end,
              file: file,
              entireFile: contents,
              content: contents.split("\n").slice(start, end).join("\n"),
            },
            newContents: contents,
            changeType,
            hideMerge: true,
            instructions: instructions.trim(),
            isLoading: false,
            openReadOnlyFiles: false,
            readOnlySnippets: {},
          } as FileChangeRequest)
          console.log(fileChangeRequests)
        }
        setCurrentFileChangeRequests(fileChangeRequests)
        if (planRef.current) {
          planRef.current.scrollTop = planRef.current.scrollHeight || 0;
        }
      }
    } catch (e) {
      console.error(e)
    } finally {
      setIsLoading(false)
    }
  }

  const setUserSuggestion = (
    suggestion: SuggestionDataItem,
    search: string,
    highlightedDisplay: ReactNode,
    index: number,
    focused: boolean,
  ) => {
    const maxLength = 50;
    const suggestedFileName =
      suggestion.display!.length < maxLength
        ? suggestion.display
        : "..." +
        suggestion.display!.slice(
          suggestion.display!.length - maxLength,
          suggestion.display!.length,
        );
    if (index > 10) {
      return null;
    }
    return (
      <div
        className={`user ${focused ? "bg-zinc-800" : "bg-zinc-900"} p-2 text-sm hover:text-white`}
      >
        {suggestedFileName}
      </div>
    );
  };


  return (
    <div className="flex flex-col">
      <div className="flex flex-row justify-between items-center mb-2">
        <Label className="mr-2">
          Instructions
        </Label>
        {/* <Button variant="secondary">
          Search
        </Button> */}
      </div>
      <MentionsInput
        className="min-h-[100px] w-full rounded-md border border-input bg-background MentionsInput mb-2"
        placeholder="Describe the changes you want to make here."
        value={instructions}
        onChange={(e: any) => setInstructions(e.target.value)}
        onBlur={(e: any) => setInstructions(e.target.value)}
        inputRef={instructionsRef}
        autoFocus
      >
        <Mention
          trigger="@"
          data={files.map((file) => ({id: file.label, display: file.label}))}
          renderSuggestion={setUserSuggestion}
          onAdd={async (currentValue) => {
            const contents = (
              await getFile(repoName, currentValue.toString())
            ).contents;
            const newSnippet = {
              file: currentValue,
              start: 0,
              end: contents.split("\n").length,
              entireFile: contents,
              content: contents,
            } as Snippet;
            setSnippets(newSnippets => {
              return {
                ...newSnippets,
                [currentValue]: newSnippet,
              };
            })
          }}
          appendSpaceOnAdd={true}
        />
      </MentionsInput>
      <div
        hidden={Object.keys(snippets).length === 0}
        className="mb-4"
      >
        {Object.keys(snippets).map(
          (snippetFile: string, index: number) => (
            <Badge
              variant="secondary"
              key={index}
              className="bg-zinc-800 text-zinc-300 mr-1"
            >
              {
                snippetFile.split("/")[
                  snippetFile.split("/").length - 1
                ]
              }
              <FaTimes
                key={String(index) + "-remove"}
                className="bg-zinc-800 cursor-pointer ml-1"
                onClick={() => {
                  setSnippets((snippets: {[key: string]: Snippet}) => {
                    const {[snippetFile]: _, ...newSnippets} = snippets;
                    return newSnippets;
                  })
                }}
              />
            </Badge>
          ),
        )}
      </div>
      {Object.keys(snippets).length === 0 && (
        <div className="text-xs px-2 text-zinc-400">
          No files added yet. Type @ to add a file.
        </div>
      )}
      <div className="text-right mb-2">
        <Button
          className="mb-2 mt-2"
          variant="secondary"
          onClick={generatePlan}
          disabled={isLoading}
        >
          Generate Plan
        </Button>
      </div>
      <Label className="mb-2">
        Sweep&apos;s Thoughts
      </Label>
      {chainOfThought.length ? (
        <div className="rounded border p-4 mb-8 overflow-y-auto" ref={thoughtsRef}>
          <Markdown className="react-markdown max-h-[150px]">
            {chainOfThought}
          </Markdown>
        </div>
      ): (
        <div className="text-zinc-500 mb-4">
          No thoughts generated yet.
        </div>
      )}
      <div className="flex flex-row mb-2 items-center">
        <Label className="mb-0">
          Sweep&apos;s Plan
        </Label>
        <div className="grow"></div>
        <Label className="text-zinc-400 mb-0">
          Debug mode
        </Label>
        <Switch
          className="ml-2"
          checked={debugLogToggle}
          onClick={() => setDebugLogToggle(debugLogToggle => !debugLogToggle)}
        >
          Debug mode
        </Switch>
      </div>
      <div className="overflow-y-auto max-h-[300px]" ref={planRef}>
        {debugLogToggle ? (
          <CodeMirror
            value={rawResponse}
            extensions={extensions}
            // onChange={onChange}
            theme={vscodeDark}
            style={{ overflow: "auto" }}
            placeholder="Empty file"
            className="ph-no-capture"
          />
        ): (
          <>
            {currentFileChangeRequests.map((fileChangeRequest, index) => {
              const filePath = fileChangeRequest.snippet.file;
              var path = filePath.split("/");
              const fileName = path.pop();
              if (path.length > 2) {
                path = path.slice(0, 1).concat(["..."]).concat(path.slice(path.length - 1))
              }
              return (
                <div className="rounded border p-3 mb-2" key={index}>
                  <div className="flex flex-row justify-between mb-2 p-2">
                    {fileChangeRequest.changeType === "create" ? (
                      <div className="font-mono">
                        <span className="text-zinc-400">
                          {path.join("/")}/
                        </span>
                        <span>
                          {fileName}
                        </span>
                      </div>
                    ): (
                      <div className="font-mono">
                        <span className="text-zinc-400">
                          {path.join("/")}/
                        </span>
                        <span>
                          {fileName}
                        </span>
                        <span className="text-zinc-400">
                          :{fileChangeRequest.snippet.start}-{fileChangeRequest.snippet.end}
                        </span>
                      </div>
                    )}
                    <span className="font-mono text-zinc-400">
                      {capitalize(fileChangeRequest.changeType)}
                    </span>
                  </div>
                  <Markdown className="react-markdown mb-2">
                    {fileChangeRequest.instructions}
                  </Markdown>
                  {fileChangeRequest.changeType === "modify" && (
                    <>
                      <Label>
                        Snippet Preview
                      </Label>
                      <CodeMirror
                        value={fileChangeRequest.snippet.content}
                        extensions={[
                          ...extensions,
                          lineNumbers({
                            formatNumber: (num: number) => {
                              return (num + fileChangeRequest.snippet.start).toString();
                            },
                          }),
                        ]}
                        theme={vscodeDark}
                        style={{ overflow: "auto" }}
                        placeholder={"No plan generated yet."}
                        className="ph-no-capture"
                        maxHeight="150px"
                      />
                    </>
                  )}
                </div>
              )
            })}
            {currentFileChangeRequests.length === 0 && (
              <div className="text-zinc-500">
                No plan generated yet.
              </div>
            )}
          </>
        )}
      </div>
      <div className="grow"></div>
      <div className="text-right">
        <Button
          variant="secondary"
          className="bg-blue-800 hover:bg-blue-900 mt-4"
          onClick={() => setFileChangeRequests(currentFileChangeRequests)}
          disabled={isLoading}
        >
          Accept Plan
        </Button>
      </div>
    </div>
  );
}

export default DashboardPlanning;
