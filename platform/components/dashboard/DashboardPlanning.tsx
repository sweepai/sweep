import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { useEffect, useState } from "react";
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

const systemMessagePrompt = `You are a brilliant and meticulous engineer assigned to write code for the following user's concerns. Take into account the current repository's language, frameworks, and dependencies.`

const userMessagePrompt = `<user_request>
{userRequest}
</user_request>

# Task:
Reference and analyze the snippets, repo, and user request to break down the requested change and propose a highly specific plan that addresses the user's request. Mention every single change required to solve the issue.

Provide a plan to solve the issue, following these rules:
* You may only create new files and modify existing files but may not necessarily need both.
* Include the full path (e.g. src/main.py and not just main.py), using the snippets and repo_tree for reference.
* Use detailed, natural language instructions on what to modify regarding business logic, and reference files to import.
* Be concrete with instructions and do not write "identify x" or "ensure y is done". Simply write "add x" or "change y to z".

You MUST follow the following format with XML tags:

# Contextual Request Analysis:
<contextual_request_analysis>
* If a PR was referenced, outline the structure of the code changes in the PR.
* Outline the ideal plan that solves the user request by referencing the snippets, and names of entities. and any other necessary files/directories.
* Describe each <create> and <modify> section in the following plan and why it will be needed.
...
</contextual_request_analysis>

# Plan:
<plan>
<create file="file_path_1" relevant_files="space-separated list of ALL files relevant for creating file_path_1">
* Natural language instructions for creating the new file needed to solve the issue.
* Reference necessary files, imports and entity names.
...
</create>
...

<modify file="file_path_2" start_line="i" end_line="j" relevant_files="space-separated list of ALL files relevant for modifying file_path_2">
* Natural language instructions for the modifications needed to solve the issue.
* Be concise and reference necessary files, imports and entity names.
...
</modify>
...

</plan>`

const chainOfThoughtPattern = /<contextual_request_analysis>(?<content>[\s\S]*?)<\/contextual_request_analysis>/;
const fileChangeRequestPattern = /<create file="(?<cFile>.*?)" relevant_files="(?<relevant_files>.*?)">(?<cInstructions>[\s\S]*?)($|<\/create>)|<modify file="(?<mFile>.*?)" start_line="(?<startLine>.*?)" end_line="(?<endLine>.*?)" relevant_files="(.*?)">(?<mInstructions>[\s\S]*?)($|<\/modify>)/sg;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const DashboardPlanning = ({
  repoName,
}: {
  repoName: string;
}) => {
  const [instructions, setInstructions] = useLocalStorage("globalInstructions", "");
  const [snippets, setSnippets] = useLocalStorage("globalSnippets", [] as Snippet[]);
  const [rawResponse, setRawResponse] = useState("");
  const [chainOfThought, setChainOfThought] = useLocalStorage("globalChainOfThought", "");
  const [fileChangeRequests, setFileChangeRequests] = useLocalStorage("globalFileChangeRequests", [] as FileChangeRequest[]);
  const [debugLogToggle, setDebugLogToggle] = useState(false);

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
      console.log(chainOfThoughtMatch)
      const fileChangeRequestMatches = rawText.matchAll(fileChangeRequestPattern);
      console.log(fileChangeRequestMatches)
      var fileChangeRequests = [];
      for (const match of fileChangeRequestMatches) {
        const file: string = match.groups?.cFile || match.groups?.mFile;
        const relevantFiles = match.groups?.relevant_files;
        const instructions = match.groups?.cInstructions || match.groups?.mInstructions;
        const changeType = match.groups?.cInstructions ? "create" : "modify";
        const startLine = match.groups?.startLine;
        const endLine = match.groups?.endLine;
        console.log(changeType, relevantFiles, instructions, startLine, endLine)
        const contents = (await getFile(repoName, file)).contents || "";
        fileChangeRequests.push({
          snippet: {
            start: startLine || 0,
            end: endLine || contents.split("\n").length,
            file: file,
            content: contents,
          },
          newContents: contents,
          changeType,
          hideMerge: true,
          instructions: instructions,
          isLoading: false,
          openReadOnlyFiles: false,
          readOnlySnippets: {},
        } as FileChangeRequest)
        console.log(fileChangeRequests)
        setFileChangeRequests(fileChangeRequests)
      }
    }
  }

  return (
    <div className="flex flex-col">
      <div className="flex flex-row justify-between items-center mb-2">
        <Label className="mr-2">
          Instructions
        </Label>
        <Button variant="secondary">
          Search
        </Button>
      </div>
      <Textarea
        placeholder="Describe the changes you want to make here"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
      />
      <Button
        className="mt-2 mb-4"
        variant="secondary"
        onClick={generatePlan}
      >
        Generate plan
      </Button>
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
      <div className="overflow-y-auto max-h-[550px]">
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
            {fileChangeRequests.map((fileChangeRequest, index) => {
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
                  <Markdown className="react-markdown">
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
          </>
        )}
      {/* </ScrollArea> */}
      </div>
    </div>
  );
}

export default DashboardPlanning;
