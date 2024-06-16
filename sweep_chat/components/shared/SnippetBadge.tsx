import { typeNameToColor, codeStyle } from "@/lib/constants";
import { sliceLines } from "@/lib/str_utils";
import { Snippet } from "@/lib/types";
import { HoverCard, HoverCardTrigger, HoverCardContent } from "@/components/ui/hover-card";
import SyntaxHighlighter from "react-syntax-highlighter";
import { Button } from "../ui/button";

const MutePath = ({ path }: { path: string }) => {
  return (
    <span>
      <span className="text-gray-400">{path.substring(0, path.lastIndexOf('/') + 1)}</span>
      <span className="text-white">{path.substring(path.lastIndexOf('/') + 1)}</span>
    </span>
  );
}

const SnippetBadge = ({
  snippet,
  className,
  repoName,
  branch,
  button,
}: {
  snippet: Snippet;
  className?: string;
  repoName: string;
  branch: string;
  button?: JSX.Element;
}) => {
  return (
    <HoverCard openDelay={300} closeDelay={200}>
      <div className={`p-2 rounded-xl mb-2 text-xs inline-block mr-2 ${typeNameToColor[snippet.type_name]} ${className || ""} `} style={{ opacity: `${Math.max(Math.min(1, snippet.score), 0.2)}` }}>
        <HoverCardTrigger asChild>
          <Button variant="link" className="text-sm py-0 px-1 h-6 leading-4" onClick={() => {
            window.open(`https://github.com/${repoName}/blob/${branch}/${snippet.file_path}`, "_blank")
          }}>
            <span>
              {snippet.end > snippet.content.split('\n').length - 3 && snippet.start == 0 ?
                <MutePath path={snippet.file_path} /> : (
                  <>
                    <MutePath path={snippet.file_path}/>
                    <span className="text-gray-400">:{snippet.start}-{snippet.end}</span>
                  </>
                )
              }
            </span>
            {
              snippet.type_name !== "source" && (
                <code className="ml-2 bg-opacity-20 bg-black text-white rounded p-1 px-2 text-xs">{snippet.type_name}</code>
              )
            }
          </Button>
        </HoverCardTrigger>
      </div>
      <HoverCardContent className="w-[800px] mr-2" style={{ opacity: 1 }}>
        <SyntaxHighlighter
          PreTag="div"
          language="python"
          style={codeStyle}
          customStyle={{
            backgroundColor: 'transparent',
            whiteSpace: 'pre-wrap',
          }}
          className="rounded-xl max-h-[600px] overflow-y-auto p-4 w-full"
        >
          {sliceLines(snippet.content, snippet.start, snippet.end)}
        </SyntaxHighlighter>
      </HoverCardContent>
    </HoverCard>
  )
}

export { SnippetBadge }

