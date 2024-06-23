import { PullRequest } from '@/lib/types'
import { sum } from 'lodash'
import { FaArrowsRotate } from 'react-icons/fa6'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { Button } from '@/components/ui/button'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { codeStyle } from '@/lib/constants'
import { renderPRDiffs } from '@/lib/str_utils'

const PullRequestHeader = ({ pr }: { pr: PullRequest }) => {
  return (
    <div
      className="bg-zinc-800 rounded-xl p-4 mb-4 text-left hover:bg-zinc-700 hover:cursor-pointer max-w-[800px]"
      onClick={() => {
        window.open(
          `https://github.com/${pr.repo_name}/pull/${pr.number}`,
          '_blank'
        )
      }}
    >
      <div
        className={`border-l-4 ${
          pr.status === 'open'
            ? 'border-green-500'
            : pr.status === 'merged'
              ? 'border-purple-500'
              : 'border-red-500'
        } pl-4`}
      >
        <div className="mb-2 font-bold text-md">
          #{pr.number} {pr.title}
        </div>
        <div className="mb-4 text-sm">{pr.body}</div>
        <div className="text-xs text-zinc-300">
          <div className="mb-1">{pr.repo_name}</div>
          {pr.file_diffs.length} files changed{' '}
          <span className="text-green-500">
            +{sum(pr.file_diffs.map((diff) => diff.additions))}
          </span>{' '}
          <span className="text-red-500">
            -{sum(pr.file_diffs.map((diff) => diff.deletions))}
          </span>
        </div>
      </div>
    </div>
  )
}

const PullRequestContent = ({ pr }: { pr: PullRequest }) => {
  return (
    <>
      <div className="p-4">
        <h2 className="text-sm font-semibold mb-2">Files changed</h2>
        <div className="text-sm text-gray-300">
          <ol>
            {pr.file_diffs.map((file, index) => (
              <li key={index} className="mb-1">
                {file.filename}{' '}
                <span
                  className={`${
                    file.status === 'added'
                      ? 'text-green-500'
                      : file.status === 'removed'
                        ? 'text-red-500'
                        : 'text-gray-400'
                  }`}
                >
                  {file.status === 'added' ? (
                    <span className="text-green-500">
                      Added (+{file.additions})
                    </span>
                  ) : file.status === 'removed' ? (
                    <span className="text-red-500">
                      Deleted ({file.deletions})
                    </span>
                  ) : (
                    <>
                      <span className="text-green-500">+{file.additions}</span>{' '}
                      <span className="text-red-500">-{file.deletions}</span>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <SyntaxHighlighter
        language="diff"
        style={codeStyle}
        customStyle={{
          backgroundColor: 'transparent',
          whiteSpace: 'pre-wrap',
        }}
        className="rounded-xl p-4 text-xs w-full"
      >
        {renderPRDiffs(pr)}
      </SyntaxHighlighter>
    </>
  )
}

export default function PullRequestDisplay({
  pr,
  onValidatePR,
}: {
  pr: PullRequest
  onValidatePR?: (pr: PullRequest) => void
}) {
  return (
    <div>
      <HoverCard openDelay={300} closeDelay={200}>
        <HoverCardTrigger>
          <PullRequestHeader pr={pr} />
        </HoverCardTrigger>
        <HoverCardContent className="w-[800px] max-h-[600px] overflow-y-auto">
          <PullRequestContent pr={pr} />
        </HoverCardContent>
      </HoverCard>
      {onValidatePR && (
        <Button
          variant="secondary"
          className="bg-zinc-800 text-white mb-4"
          onClick={() => onValidatePR(pr)}
        >
          <FaArrowsRotate className="inline-block mr-2" />
          Re-validate Pull Request
        </Button>
      )}
    </div>
  )
}