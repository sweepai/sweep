import { Dispatch, SetStateAction } from 'react'
import CodeMirrorMerge from 'react-codemirror-merge'
import CodeMirror from '@uiw/react-codemirror'
import { dracula } from '@uiw/codemirror-theme-dracula'
import { EditorView } from 'codemirror'
import { StatefulCodeSuggestion } from '@/lib/types'
import { languageMapping } from '@/lib/constants'
import { debounce } from 'lodash'

const Original = CodeMirrorMerge.Original
const Modified = CodeMirrorMerge.Modified

export default function CodeMirrorEditor({
  suggestion,
  index,
  setSuggestedChanges,
}: {
  suggestion: StatefulCodeSuggestion
  index: number
  setSuggestedChanges: Dispatch<SetStateAction<StatefulCodeSuggestion[]>>
}) {
  const fileExtension = suggestion.filePath.split('.').pop()
  // default to javascript
  let languageExtension = languageMapping['js']
  if (fileExtension) {
    languageExtension = languageMapping[fileExtension]
  }

  if (suggestion.originalCode.length === 0) {
    return (
      <CodeMirror
        theme={dracula}
        autoFocus={false}
        key={JSON.stringify(suggestion)}
        value={suggestion.newCode}
        readOnly={!(suggestion.state == 'done' || suggestion.state == 'error')}
        extensions={[
          EditorView.editable.of(
            suggestion.state == 'done' || suggestion.state == 'error'
          ),
          ...(languageExtension ? [languageExtension] : []),
        ]}
        onChange={debounce((value: string) => {
          setSuggestedChanges((suggestedChanges) =>
            suggestedChanges.map((suggestion, i) =>
              i == index ? { ...suggestion, newCode: value } : suggestion
            )
          )
        }, 1000)}
      />
    )
  }

  return (
    <CodeMirrorMerge
      theme={dracula}
      revertControls={'a-to-b'}
      collapseUnchanged={{
        margin: 3,
        minSize: 4,
      }}
      autoFocus={false}
      key={JSON.stringify(suggestion)}
    >
      <Original
        value={suggestion.originalCode}
        readOnly={true}
        extensions={[
          EditorView.editable.of(false),
          ...(languageExtension ? [languageExtension] : []),
        ]}
      />
      <Modified
        value={suggestion.newCode}
        readOnly={!(suggestion.state == 'done' || suggestion.state == 'error')}
        extensions={[
          EditorView.editable.of(
            suggestion.state == 'done' || suggestion.state == 'error'
          ),
          ...(languageExtension ? [languageExtension] : []),
        ]}
        onChange={debounce((value: string) => {
          setSuggestedChanges((suggestedChanges) =>
            suggestedChanges.map((suggestion, i) =>
              i == index ? { ...suggestion, newCode: value } : suggestion
            )
          )
        }, 1000)}
      />
    </CodeMirrorMerge>
  )
}

