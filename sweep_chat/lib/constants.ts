import { dracula } from "react-syntax-highlighter/dist/cjs/styles/prism";

const codeStyle = dracula;

const modelMap: Record<string, string> = {
  "claude-3-opus-20240229": "Opus",
  "claude-3-sonnet-20240229": "Sonnet",
  "claude-3-haiku-20240307": "Haiku",
  "gpt-4o": "GPT-4o",
}

const DEFAULT_K: number = 8

export { codeStyle, modelMap, DEFAULT_K }
