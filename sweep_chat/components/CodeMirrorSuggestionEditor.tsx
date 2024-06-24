import { Dispatch, SetStateAction, useEffect, useRef, useState } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { dracula } from '@uiw/codemirror-theme-dracula'
import { EditorView } from 'codemirror'
import { StatefulCodeSuggestion } from '@/lib/types'
import { languageMapping } from '@/lib/constants'
import { Switch } from '@/components/ui/switch'
import { debounce } from 'lodash'
// @ts-ignore
import * as Diff from 'diff'
import CodeMirrorMerge from 'react-codemirror-merge'

const Original = CodeMirrorMerge.Original
const Modified = CodeMirrorMerge.Modified

export default function CodeMirrorSuggestionEditor({
  suggestion,
  index,
  setSuggestedChanges,
  showOriginal = true,
}: {
  suggestion: StatefulCodeSuggestion
  index: number
  setSuggestedChanges: Dispatch<SetStateAction<StatefulCodeSuggestion[]>>
  showOriginal?: boolean
}) {
  const fileExtension = suggestion.filePath.split('.').pop()
  // default to javascript
  let languageExtension = languageMapping['js']
  if (fileExtension) {
    languageExtension = languageMapping[fileExtension]
  }

  return (
    <>
      <CodeMirrorMerge
        theme={dracula}
        revertControls={showOriginal ? 'a-to-b' : undefined}
        collapseUnchanged={{
          margin: 3,
          minSize: 4,
        }}
        autoFocus={false}
        key={JSON.stringify(suggestion)}
        className={showOriginal ? "" : "hideOriginal"}
      >
        <Original
          value={suggestion.originalCode}
          readOnly={true}
          extensions={[
            EditorView.editable.of(false),
            EditorView.lineWrapping,
            ...(languageExtension ? [languageExtension] : []),
          ]} />
        <Modified
          value={suggestion.newCode}
          readOnly={!(suggestion.state == 'done' || suggestion.state == 'error')}
          extensions={[
            EditorView.editable.of(
              suggestion.state == 'done' || suggestion.state == 'error'
            ),
            EditorView.lineWrapping,
            ...(languageExtension ? [languageExtension] : []),
          ]}
          onChange={debounce((value: string) => {
            setSuggestedChanges((suggestedChanges) => suggestedChanges.map((suggestion, i) => i == index ? { ...suggestion, newCode: value } : suggestion
            )
            )
          }, 1000)} />
      </CodeMirrorMerge>
    </>
  )
}

