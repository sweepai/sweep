interface File {
  name: string;
  path: string;
  isDirectory: boolean;
  content?: string;
  snippets?: Snippet[];
}

interface Snippet {
  file: string;
  start: number;
  end: number;
  entireFile: string;
  content: string;
}

interface FileChangeRequest {
  snippet: Snippet;
  instructions: string;
  newContents: string;
  changeType: "create" | "modify";
  hideMerge: boolean;
  isLoading: boolean;
  readOnlySnippets: { [key: string]: Snippet };
  diff: string;
  status: "queued" | "in-progress" | "done" | "error" | "idle";
}

const fcrEqual = (a: FileChangeRequest, b: FileChangeRequest) => {
  return (
    a.snippet.file === b.snippet.file &&
    a.snippet.start === b.snippet.start &&
    a.snippet.end === b.snippet.end
  );
};

const snippetKey = (snippet: Snippet) => {
  return `${snippet.file}:${snippet.start || 0}-${snippet.end || 0}`;
};

interface Message {
  role: "user" | "system" | "assistant";
  content: string;
}

export { fcrEqual, snippetKey };
export type { File, Snippet, FileChangeRequest, Message };
