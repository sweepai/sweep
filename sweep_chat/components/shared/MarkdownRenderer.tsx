import { codeStyle } from '@/lib/constants'
import Markdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import remarkGfm from 'remark-gfm'
// @ts-ignore
import * as Diff from 'diff'

const CODE_CHANGE_PATTERN =
  /<code_change>\s*<file_path>\n*(?<filePath>[\s\S]+?)\n*<\/file_path>\s*(<original_code>\n*(?<originalCode>[\s\S]*?)\n*)?($|<\/original_code>\s*)?($|<new_code>\n*(?<newCode>[\s\S]+?)\n*($|<\/new_code>)\s*($|(?<closingTag><\/code_change>)))/gs

const MarkdownRenderer = ({
  content,
  className,
}: {
  content: string
  className?: string
}) => {
  const matches = Array.from(content.matchAll(CODE_CHANGE_PATTERN))
  let transformedContent = content

  for (const match of matches) {
    let {
      filePath,
      originalCode = '',
      newCode,
      closingTag,
    } = match.groups || {}
    if (newCode == null) {
      transformedContent = transformedContent.replace(
        match[0],
        `**Suggestions for \`${filePath}\`:**\n\`\`\`diff\n${originalCode}\n\`\`\``
      )
    } else {
      let diffLines = Diff.diffLines(originalCode.trim(), newCode.trim())
      if (!closingTag) {
        if (diffLines.length >= 2) {
          const lastDiff = diffLines[diffLines.length - 1]
          const secondLastDiff = diffLines[diffLines.length - 2]
          if (
            lastDiff.added &&
            lastDiff.value.trim().split('\n').length === 1 &&
            secondLastDiff.removed &&
            secondLastDiff.value.trim().split('\n').length > 1
          ) {
            const temp = diffLines[diffLines.length - 1]
            diffLines[diffLines.length - 1] = diffLines[diffLines.length - 2]
            diffLines[diffLines.length - 2] = temp
            diffLines[diffLines.length - 2].value = ''
            diffLines[diffLines.length - 1].removed = false
          }
        }
      }
      const formattedChange =
        `**Suggestions for \`${filePath}\`**\n\`\`\`diff\n` +
        diffLines
          .map(
            (
              {
                added,
                removed,
                value,
              }: { added: boolean; removed: boolean; value: string },
              index: number
            ): string => {
              let symbol = added ? '+' : removed ? '-' : ' '
              if (
                index === diffLines.length - 1 &&
                index === diffLines.length - 2 &&
                removed &&
                !closingTag
              ) {
                symbol = ' '
              }
              const results =
                symbol + value.trimEnd().replaceAll('\n', '\n' + symbol)
              return results
            }
          )
          .join('\n') +
        '\n```'
      transformedContent = transformedContent.replace(match[0], formattedChange)
    }
  }

  return (
    <Markdown
      className={`${className} reactMarkdown`}
      remarkPlugins={[remarkGfm]}
      components={{
        code(props) {
          const { children, className, node, ref, ...rest } = props
          const match = /language-(\w+)/.exec(className || '')
          return match ? (
            <SyntaxHighlighter
              {...rest} // eslint-disable-line
              PreTag="div"
              language={match[1]}
              style={codeStyle}
              customStyle={{
                backgroundColor: '#333',
              }}
              className="rounded-xl"
            >
              {String(children).replace(/\n$/, '')}
            </SyntaxHighlighter>
          ) : (
            <code {...rest} className={`rounded-xl ${className}`}>
              {children}
            </code>
          )
        },
      }}
    >
      {transformedContent}
    </Markdown>
  )
}

export { CODE_CHANGE_PATTERN, MarkdownRenderer }
