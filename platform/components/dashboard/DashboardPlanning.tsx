import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { useEffect, useRef, useState } from "react";
import CodeMirror, { EditorView, keymap } from "@uiw/react-codemirror";
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

const systemMessagePrompt = `You are a brilliant and meticulous engineer assigned to plan code changes for the following user's concerns. Take into account the current repository's language, frameworks, and dependencies.`

const userMessagePrompt = `<user_request>
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

const chainOfThoughtPattern = /<contextual_request_analysis>(?<content>[\s\S]*?)($|<\/contextual_request_analysis>)/;
const fileChangeRequestPattern = /<create file="(?<cFile>.*?)" relevant_files="(?<relevant_files>.*?)">(?<cInstructions>[\s\S]*?)($|<\/create>)|<modify file="(?<mFile>.*?)" start_line="(?<startLine>.*?)" end_line="(?<endLine>.*?)" relevant_files="(.*?)">(?<mInstructions>[\s\S]*?)($|<\/modify>)/sg;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const DashboardPlanning = ({
  repoName,
  setFileChangeRequests,
}: {
  repoName: string;
  setFileChangeRequests: (fileChangeRequests: FileChangeRequest[]) => void;
}) => {
  const [instructions, setInstructions] = useLocalStorage("globalInstructions", "");
  const [snippets, setSnippets] = useLocalStorage("globalSnippets", [] as Snippet[]);
  const [rawResponse, setRawResponse] = useLocalStorage("planningRawResponse", "");
  const [chainOfThought, setChainOfThought] = useLocalStorage("globalChainOfThought", "");
  const [currentFileChangeRequests, setCurrentFileChangeRequests] = useLocalStorage("globalFileChangeRequests", [] as FileChangeRequest[]);
  const [debugLogToggle, setDebugLogToggle] = useState(false);

  const thoughtsRef = useRef<HTMLDivElement>(null);
  const planRef = useRef<HTMLDivElement>(null);

  const extensions = [
    xml(),
    EditorView.lineWrapping,
    keymap.of([indentWithTab]),
    indentUnit.of("    "),
  ];

  const generatePlan = async () => {
    console.log("Generating plan...")
    console.log(instructions)
    const response = await fetch("/api/openai/edit", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        userMessage: userMessagePrompt
          .replace("{userRequest}", instructions),
        systemMessagePrompt,
        snippets
      }),
    })
    const reader = response.body?.getReader();
    const decoder = new TextDecoder("utf-8");
    let rawText = "";
    setCurrentFileChangeRequests([])
    while (true) {
      const { done, value } = await reader?.read()!
      if (done) {
        break;
      }
      const text = decoder.decode(value);
      rawText += text;
      console.log(rawText)
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
        const startLine: string | undefined = match.groups?.startLine;
        const endLine: string | undefined = match.groups?.endLine;
        console.log(changeType, relevantFiles, instructions, startLine, endLine)
        const contents = (await getFile(repoName, file)).contents || "";
        fileChangeRequests.push({
          snippet: {
            start: startLine ? parseInt(startLine) : 0,
            end: endLine ? parseInt(endLine) : contents.split("\n").length,
            file: file,
            content: contents,
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
  }

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
      <Textarea
        className="mb-4"
        placeholder="Describe the changes you want to make here"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
      />
      <div className="text-center mb-4">
        <Button
          className="mb-4"
          variant="secondary"
          onClick={generatePlan}
        >
          Generate Plan
        </Button>
      </div>
      <Label className="mb-2">
        Sweep&apos;s Thoughts
      </Label>
      <div className="rounded border p-4 mb-8 overflow-y-auto" ref={thoughtsRef}>
        <Markdown className="react-markdown max-h-[150px]">
          {chainOfThought}
        </Markdown>
      </div>
      <div className="flex flex-row mb-2 items-center">
        <Label>
          Sweep&apos;s Plan
        </Label>
        <div className="grow"></div>
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
              const path = filePath.split("/");
              const fileName = path.pop();
              return (
                <div className="rounded border p-3 mb-2" key={index}>
                  <div className="flex flex-row justify-between mb-2 p-2">
                    {fileChangeRequest.changeType === "create" ? (
                      <div className="font-mono">
                        <span className="text-zinc-400">
                          {path}/
                        </span>
                        <span>
                          {fileName}
                        </span>
                      </div>
                    ): (
                      <div className="font-mono">
                        <span className="text-zinc-400">
                          {path}/
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
                    <CodeMirror
                      value={fileChangeRequest.snippet.content.split("\n").slice(0, 5).join()}
                      extensions={extensions}
                      theme={vscodeDark}
                      style={{ overflow: "auto" }}
                      placeholder={"No plan generated yet."}
                      className="ph-no-capture"
                    />
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
      <div className="text-center">
        <Button
          variant="secondary"
          className="bg-blue-800 hover:bg-blue-900 mt-4"
          onClick={() => setFileChangeRequests(currentFileChangeRequests)}
        >
          Accept Plan
        </Button>
      </div>
    </div>
  );
}

export default DashboardPlanning;
