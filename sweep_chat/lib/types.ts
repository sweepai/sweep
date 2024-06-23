type Tail<T extends any[]> = T extends [any, ...infer U] ? U : never;

type SnakeCase<S extends string> = S extends `${infer T}${infer U}`
  ? U extends Uncapitalize<U>
    ? `${Lowercase<T>}${SnakeCase<U>}`
    : `${Lowercase<T>}_${SnakeCase<U>}`
  : S

type SnakeCaseKeys<T> = {
  [K in keyof T as SnakeCase<string & K>]: T[K] extends object
    ? SnakeCaseKeys<T[K]>
    : T[K]
}

type Repository = any

interface Snippet {
  content: string
  start: number
  end: number
  file_path: string
  type_name: 'source' | 'tests' | 'dependencies' | 'tools' | 'docs'
  score: number
}

interface FileDiff {
  sha: string
  filename: string
  status:
    | 'modified'
    | 'added'
    | 'removed'
    | 'renamed'
    | 'copied'
    | 'changed'
    | 'unchanged'
  additions: number
  deletions: number
  changes: number
  blob_url: string
  raw_url: string
  contents_url: string
  patch?: string | undefined
  previous_filename?: string | undefined
}

interface PullRequest {
  number: number
  repo_name: string
  title: string
  body: string
  labels: string[]
  status: string
  file_diffs: FileDiff[]
  branch: string
}

interface CodeSuggestion {
  filePath: string
  originalCode: string
  newCode: string
  fileContents: string
}

interface StatefulCodeSuggestion extends CodeSuggestion {
  state: 'pending' | 'processing' | 'done' | 'error'
  error?: string
}

interface Message {
  content: string // This is the message content or function output
  role: 'user' | 'assistant' | 'function'
  function_call?: {
    function_name: string
    function_parameters: Record<string, any>
    is_complete: boolean
    snippets?: Snippet[]
  } // This is the function input
  annotations?: {
    pulls?: PullRequest[]
    codeSuggestions?: StatefulCodeSuggestion[]
    prValidationStatuses?: PrValidationStatus[]
  }
}

interface ChatSummary {
  messagesId: string
  createdAt: string
  initialMessage: string
}

interface PrValidationStatus {
  message: string
  stdout: string
  succeeded: boolean | null
  status: 'pending' | 'running' | 'success' | 'failure' | 'cancelled'
  llmMessage: string
  containerName: string
}

export type {
  Tail,
  SnakeCase,
  SnakeCaseKeys,
  Repository,
  Snippet,
  FileDiff,
  PullRequest,
  Message,
  CodeSuggestion,
  StatefulCodeSuggestion,
  ChatSummary,
  PrValidationStatus,
}
