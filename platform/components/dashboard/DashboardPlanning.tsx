import { useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { useEffect, useState } from "react";
import { Snippet } from "@/lib/types";
import { ScrollArea } from "../ui/scroll-area";
import { Button } from "../ui/button";

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

</plan>"""`

const DashboardPlanning = ({
  repoName,
}: {
  repoName: string;
}) => {
  const [instructions, setInstructions] = useLocalStorage("globalInstructions", "");
  const [snippets, setSnippets] = useLocalStorage("globalSnippets", [] as Snippet[]);
  const [rawResponse, setRawResponse] = useState("");

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
    }
  }

  return (
    <>
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
        variant="secondary"
        onClick={generatePlan}
      >
        Generate plan
      </Button>
      <br/><br/>
      <Label>
        Sweep&apos;s Plan
      </Label>
      <ScrollArea className="rounded border overflow-y-auto min-h-[50px] p-2 font-mono">
        {rawResponse.replace("\n", "<br/>")}
      </ScrollArea>
    </>
  );
}

export default DashboardPlanning;
