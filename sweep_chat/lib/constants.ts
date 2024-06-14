import { dracula } from "react-syntax-highlighter/dist/cjs/styles/prism";

const codeStyle = dracula;

const modelMap: Record<string, string> = {
  "claude-3-opus-20240229": "Opus",
  "claude-3-sonnet-20240229": "Sonnet",
  "claude-3-haiku-20240307": "Haiku",
  "gpt-4o": "GPT-4o",
}

const roleToColor = {
  "user": "bg-zinc-600",
  "assistant": "bg-zinc-700",
  "function": "bg-zinc-800",
}

const typeNameToColor = {
  "source": "bg-blue-900",
  "tests": "bg-green-900",
  "dependencies": "bg-zinc-600",
  "tools": "bg-purple-900",
  "docs": "bg-yellow-900",
}

const DEFAULT_K: number = 8

export { codeStyle, modelMap, DEFAULT_K, roleToColor, typeNameToColor }
