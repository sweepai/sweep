type Repository = any;

interface Snippet {
  content: string;
  start: number;
  end: number;
  file_path: string;
  type_name: "source" | "tests" | "dependencies" | "tools" | "docs";
  score: number;
}

interface FileDiff {
  sha: string;
  filename: string;
  status: "modified" | "added" | "removed" | "renamed" | "copied" | "changed" | "unchanged";
  additions: number;
  deletions: number;
  changes: number;
  blob_url: string;
  raw_url: string;
  contents_url: string;
  patch?: string | undefined;
  previous_filename?: string | undefined;
}

interface PullRequest {
  number: number;
  repo_name: string;
  title: string;
  body: string;
  labels: string[];
  status: string;
  file_diffs: FileDiff[]
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
  annotations?: {
    pulls?: PullRequest[]
  }
}

interface CodeSuggestion {
  filePath: string;
  originalCode: string;
  newCode: string;
}

interface StatefulCodeSuggestion extends CodeSuggestion {
  state: "pending" | "processing" | "done" | "error";
  error?: string;
}

export type {
    Repository,
    Snippet,
    FileDiff,
    PullRequest,
    Message,
    CodeSuggestion,
    StatefulCodeSuggestion,
}
