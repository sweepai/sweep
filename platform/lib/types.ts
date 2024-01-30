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
  newContent: string | undefined;
  changeType: "create" | "modify";
}

export type { File, Snippet, FileChangeRequest };
