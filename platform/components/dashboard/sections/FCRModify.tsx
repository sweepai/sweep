import React, { ReactNode, memo } from "react";
import { getFile } from "../../../lib/api.service";
import { Snippet } from "../../../lib/search";
import { FileChangeRequest, snippetKey } from "../../../lib/types";
import { FaPlay, FaTimes } from "react-icons/fa";
import { FaStop, FaTrash } from "react-icons/fa6";
import { Badge } from "../../ui/badge";
import { Draggable } from "react-beautiful-dnd";
import { MentionsInput, Mention, SuggestionDataItem } from "react-mentions";
import { Button } from "../../ui/button";
import { useRecoilState } from "recoil";
import { FileChangeRequestsState } from "../../../state/fcrAtoms";
import {
  setStatusForFCR,
  removeFileChangeRequest,
  setReadOnlySnippetForFCR,
  removeReadOnlySnippetForFCR,
} from "../../../state/fcrStateHelpers";

const instructionsPlaceholder = `Instructions for what to modify. Type "@filename" for Sweep to read another file.`;

const capitalize = (s: string) => {
  return s.charAt(0).toUpperCase() + s.slice(1);
};

const FCRModify = memo(function FCRModify({
  repoName,
  setCurrentFileChangeRequestIndex,
  getFileChanges,
  isRunningRef,
  fcr,
  index,
  getDynamicClassNames,
  getItemStyle,
  mentionFiles,
  fcrInstructions,
  setFCRInstructions,
  setUserSuggestion,
}: {
  repoName: string;
  setCurrentFileChangeRequestIndex: React.Dispatch<
    React.SetStateAction<number>
  >;
  getFileChanges: (
    fileChangeRequest: FileChangeRequest,
    index: number,
  ) => Promise<void>;
  isRunningRef: React.MutableRefObject<boolean>;
  fcr: FileChangeRequest;
  index: number;
  getDynamicClassNames: (fcr: FileChangeRequest, index: number) => string;
  getItemStyle: (isDragging: boolean, draggableStyle: any) => any;
  mentionFiles: { id: any; display: any }[];
  fcrInstructions: { [key: string]: string };
  setFCRInstructions: React.Dispatch<
    React.SetStateAction<{ [key: string]: string }>
  >;
  setUserSuggestion: (
    suggestion: SuggestionDataItem,
    search: string,
    highlightedDisplay: ReactNode,
    index: number,
    focused: boolean,
  ) => JSX.Element | null;
}) {
  const [fileChangeRequests, setFileChangeRequests] = useRecoilState(
    FileChangeRequestsState,
  );
  return (
    <Draggable
      key={snippetKey(fcr.snippet)}
      draggableId={snippetKey(fcr.snippet)}
      index={index}
    >
      {(provided: any, snapshot: any) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          style={getItemStyle(
            snapshot.isDragging,
            provided.draggableProps.style,
          )}
        >
          <div
            key={index}
            className="mb-4 grow border rounded"
            onClick={(e) => {
              setCurrentFileChangeRequestIndex(index);
            }}
          >
            <div
              className={`justify-between p-2 ${getDynamicClassNames(fcr, index)} rounded font-sm font-mono items-center`}
            >
              <div className="flex flex-row w-full items-center">
                <span>
                  {
                    fcr.snippet.file.split("/")[
                      fcr.snippet.file.split("/").length - 1
                    ]
                  }
                  :{fcr.snippet.start}-{fcr.snippet.end}
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  className="mr-2 ml-auto"
                  onClick={async () => {
                    removeFileChangeRequest(
                      fcr,
                      fileChangeRequests,
                      setFileChangeRequests,
                    );
                    setFCRInstructions((prev: any) => {
                      return {
                        ...prev,
                        [snippetKey(fcr.snippet)]: "",
                      };
                    });
                  }}
                  disabled={fcr.isLoading}
                >
                  <FaTrash />
                </Button>
              </div>
            </div>
            <MentionsInput
              className="min-h-[50px] w-full rounded-md border border-input bg-background MentionsInput mb-2"
              placeholder={instructionsPlaceholder}
              value={fcrInstructions[snippetKey(fcr.snippet)] || ""}
              onKeyUp={(e: any) => {
                if (e.key === "Enter" && e.ctrlKey && !isRunningRef.current) {
                  getFileChanges(fcr, index);
                }
              }}
              onClick={(e: any) => {
                setCurrentFileChangeRequestIndex(index);
              }}
              onChange={(e: any) => {
                setFileChangeRequests((prev: FileChangeRequest[]) => [
                  ...prev.slice(0, index),
                  {
                    ...prev[index],
                    instructions: e.target.value,
                  },
                  ...prev.slice(index + 1),
                ]);
                setFCRInstructions((prev: any) => {
                  return {
                    ...prev,
                    [snippetKey(fcr.snippet)]: e.target.value,
                  };
                });
              }}
              onBlur={(e: any) => {
                // this apparently removes the styling on the mentions, this may be a hack
                setFileChangeRequests((prev: FileChangeRequest[]) => [
                  ...prev.slice(0, index),
                  {
                    ...prev[index],
                    instructions: e.target.value,
                  },
                  ...prev.slice(index + 1),
                ]);
              }}
            >
              <Mention
                className="Mention"
                trigger="@"
                data={mentionFiles}
                renderSuggestion={setUserSuggestion}
                onAdd={async (currentValue) => {
                  const contents = (
                    await getFile(repoName, currentValue.toString())
                  ).contents;
                  const newSnippet = {
                    file: currentValue,
                    start: 0,
                    end: contents.split("\n").length,
                    entireFile: contents,
                    content: contents, // this is the slice based on start and end, remeber to change this
                  } as Snippet;
                  setReadOnlySnippetForFCR(
                    fcr,
                    newSnippet,
                    fileChangeRequests,
                    setFileChangeRequests,
                  );
                }}
                appendSpaceOnAdd={true}
                // shift it down 5px
              />
            </MentionsInput>
            <div
              hidden={Object.keys(fcr.readOnlySnippets).length === 0}
              className="mb-2"
            >
              {Object.keys(fcr.readOnlySnippets).map(
                (snippetFile: string, index: number) => (
                  <Badge
                    variant="secondary"
                    key={index}
                    className="bg-zinc-800 text-zinc-300"
                  >
                    {snippetFile.split("/")[snippetFile.split("/").length - 1]}
                    <FaTimes
                      key={String(index) + "-remove"}
                      className="bg-zinc-800 cursor-pointer"
                      onClick={() => {
                        removeReadOnlySnippetForFCR(
                          fcr,
                          snippetFile,
                          fileChangeRequests,
                          setFileChangeRequests,
                        );
                      }}
                    />
                  </Badge>
                ),
              )}
            </div>
            {Object.keys(fcr.readOnlySnippets).length === 0 && (
              <div className="text-xs px-2 text-zinc-400">
                No files added yet. Type @ to add a file.
              </div>
            )}
            <div className="flex flex-row justify-end w-full pb-2">
              <span>
                {!isRunningRef.current ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mr-2"
                    onClick={(e: any) => {
                      setCurrentFileChangeRequestIndex(index);
                      getFileChanges(fcr, index);
                    }}
                    disabled={fcr.isLoading}
                  >
                    <FaPlay />
                    &nbsp;{capitalize(fcr.changeType)}
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mr-2"
                    onClick={(e: any) => {
                      isRunningRef.current = false;
                      setStatusForFCR(
                        "idle",
                        fcr,
                        fileChangeRequests,
                        setFileChangeRequests,
                      );
                    }}
                  >
                    <FaStop />
                    &nbsp;Cancel
                  </Button>
                )}
              </span>
            </div>
          </div>
        </div>
      )}
    </Draggable>
  );
});

export default FCRModify;
