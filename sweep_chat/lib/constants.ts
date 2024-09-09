import { javascript } from '@codemirror/lang-javascript'
import { go } from '@codemirror/lang-go'
import { python } from '@codemirror/lang-python'
import { dracula } from 'react-syntax-highlighter/dist/cjs/styles/prism'
import { Extension } from '@uiw/react-codemirror'

const codeStyle = dracula

const modelMap: Record<string, string> = {
  'claude-3-5-sonnet-20240620': 'Sonnet 3.5',
  'claude-3-opus-20240229': 'Opus',
  'claude-3-sonnet-20240229': 'Sonnet',
  'claude-3-haiku-20240307': 'Haiku',
  'gpt-4o': 'GPT-4o',
}

const roleToColor = {
  user: 'bg-zinc-600',
  assistant: 'bg-zinc-700',
  function: 'bg-zinc-800',
}

const typeNameToColor = {
  source: 'bg-blue-900',
  tests: 'bg-green-900',
  dependencies: 'bg-zinc-600',
  tools: 'bg-purple-900',
  docs: 'bg-yellow-900',
}

const languageMapping: Record<string, Extension> = {
  js: javascript(),
  jsx: javascript({ jsx: true }),
  ts: javascript({ typescript: true }),
  tsx: javascript({ typescript: true, jsx: true }),
  go: go(),
  py: python(),
}

const DEFAULT_K: number = 8
const DEFAULT_MODEL = 'claude-3-5-sonnet-20240620'

export {
  codeStyle,
  modelMap,
  DEFAULT_K,
  DEFAULT_MODEL,
  roleToColor,
  typeNameToColor,
  languageMapping,
}
