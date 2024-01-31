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
  openReadOnlyFiles: boolean;
  readOnlySnippets: { [key: string]: Snippet };
}

interface Message {
  role: "user" | "system" | "assistant";
  content: string;
}

export type { File, Snippet, FileChangeRequest, Message };
