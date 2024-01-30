import { Snippet } from "../../lib/search";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "../ui/resizable";
import { Textarea } from "../ui/textarea";
import React, { useCallback, useEffect, useState } from "react";
import FileSelector, { getLanguage } from "../shared/FileSelector";
import DashboardActions from "./DashboardActions";
import CodeMirror, {
  EditorView,
  gutter,
  lineNumbers,
} from "@uiw/react-codemirror";
import { useDebounce, useLocalStorage } from "usehooks-ts";
import { Label } from "../ui/label";
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";

// const debounce = (func: (...args: any[]) => void, delay: number): (() => void) => {
//     let debounceTimer: NodeJS.Timeout;
//     return function(this: any, ...args: any[]) {
//         clearTimeout(debounceTimer);
//         debounceTimer = setTimeout(() => func.apply(this, args), delay);
//     };
// }

const DashboardContext = () => {
  const [oldFile, setOldFile] = useLocalStorage("oldFile", "");
  const [hideMerge, setHideMerge] = useLocalStorage("hideMerge", true);
  const [branch, setBranch] = useLocalStorage("branch", "");
  const [filePath, setFilePath] = useLocalStorage("filePath", "");
  const [scriptOutput, setScriptOutput] = useLocalStorage("scriptOutput", "");
  const [file, setFile] = useLocalStorage("file", "");
  const [searchedSnippets, setSearchedSnippets] = useState([] as Snippet[]);
  const [searchIsLoading, setSearchIsLoading] = useState(false);
  const [repoName, setRepoName] = useLocalStorage("repoName", "");
  const [query, setQuery] = useState("");

  useEffect(() => {
    (async () => {
      const params = new URLSearchParams({ repo: repoName }).toString();
      const response = await fetch("/api/branch?" + params);
      const object = await response.json();
      setBranch(object.branch);
    })();
  }, [repoName, setBranch]);

  const [debounceTimer, setDebounceTimer] = useState<NodeJS.Timeout | null>(
    null,
  );

  useEffect(() => {
    const executeSearch = async () => {
      setSearchIsLoading(true);
      const params = new URLSearchParams({ repo: repoName, query }).toString();
      const response = await fetch("/api/files/search?" + params);
      const { snippets } = await response.json();
      setSearchedSnippets(snippets);
      setSearchIsLoading(false);
    };

    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }

    setDebounceTimer(setTimeout(executeSearch, 300));
  }, [repoName, query]);

  return (
    <>
      <h1 className="font-bold text-xl fixed">Sweep Assistant</h1>
      <div className="flex flex-col h-full mt-32 items-center">
        <div className="flex flex-col max-w-[400px]">
          <div className="flex flex-row space-between mb-4">
            <div className="mr-4">
              <Label>Repository Path</Label>
              <Input
                className="max-w-[400px]"
                value={repoName}
                onChange={(event) => setRepoName(event.target.value)}
              />
            </div>
            <div>
              <Label>Branch</Label>
              <Input
                className="max-w-[400px]"
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
              />
            </div>
          </div>
          <Label className="flex">
            Query&nbsp;
            {searchIsLoading && (
              <Skeleton className="w-[12px] h-[12px] rounded-full bg-zinc-600" />
            )}
          </Label>
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tell Sweep what you want to do..."
            autoFocus
          />
        </div>
        <div className="max-w-[1800px] mt-8 flex justify-center flex-wrap align-items-start">
          {searchedSnippets.map((snippet) => (
            <>
              <div
                key={`${snippet.file}:${snippet.start}:${snippet.end}`}
                className="border p-4 rounded-xl border p-4 rounded-xl w-[30%] min-w-[300px] m-2"
              >
                <div className="mb-2 text-blue-400">
                  <code className="whitespace-pre-wrap">
                    {snippet.file}:{snippet.start}:{snippet.end}
                  </code>
                </div>
                <CodeMirror
                  value={snippet.content}
                  extensions={[
                    getLanguage(snippet.file.split(".").pop() || "js"),
                    EditorView.lineWrapping,
                    lineNumbers({
                      formatNumber: (num: number) => {
                        return (num + snippet.start).toString();
                      },
                    }),
                  ]}
                  theme={vscodeDark}
                  style={{ overflow: "auto" }}
                  placeholder={"No text"}
                  maxHeight="300px"
                />
              </div>
              <br />
            </>
          ))}
          {searchedSnippets.length === 0 &&
            !searchIsLoading &&
            "No results found."}
        </div>
      </div>
    </>
  );
};

export default DashboardContext;
