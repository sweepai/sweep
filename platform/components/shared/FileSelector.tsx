"use client";
import React, { useCallback, useEffect, useState } from "react";

import getFiles from "../../lib/api.service";
import { vscodeDark } from "@uiw/codemirror-theme-vscode";

import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { python } from "@codemirror/lang-python";
import { html } from "@codemirror/lang-html";

import CodeMirror, {
  EditorView,
  keymap,
} from "@uiw/react-codemirror";
import CodeMirrorMerge from "react-codemirror-merge";
import { indentWithTab } from "@codemirror/commands";
import { indentUnit } from "@codemirror/language";

const getLanguage = (ext: string) => {
  const languageMap: { [key: string]: any } = {
    js: javascript(),
    jsx: javascript({ jsx: true }),
    ts: javascript({ typescript: true }),
    tsx: javascript({ typescript: true, jsx: true }),
    html: html(),
    ejs: html(),
    erb: html(),
    py: python(),
    kt: java(),
  };
  return languageMap[ext] || javascript();
};

const Original = CodeMirrorMerge.Original;
const Modified = CodeMirrorMerge.Modified;

const FileSelector = ({
  filePath,
  file,
  setFile,
  hideMerge,
  setHideMerge,
  oldFile,
  setOldFile,
  repoName,
  files,
  setFiles,
  blockedGlobs,
  fileLimit,
}: any) => {
  const [value, setValue] = useState("console.log('hello world!');");
  const placeholderText =
    "Your code will be displayed here once you select a Repository and add a file to modify.";
  const onChange = useCallback(
    (val: any, viewUpdate: any) => {
      setFile(val);
    },
    [setValue, setFile],
  );

//   const onOldChange = useCallback(
//     (val: any, viewUpdate: any) => {
//       setOldFile(val);
//     },
//     [setValue, setFile],
//   );

  const onOldChange = setOldFile;
  useEffect(() => {
    (async () => {
      let newFiles = await getFiles(repoName, blockedGlobs, fileLimit);
      newFiles = newFiles.map((file: any) => {
        return { value: file, label: file };
      });
      setFiles(newFiles);
    })();
  }, [repoName]);
  const ext = filePath?.split(".").pop() || "js";
  const languageExtension = getLanguage(ext);
  const extensions = [
    languageExtension,
    EditorView.lineWrapping,
    keymap.of([indentWithTab]),
    indentUnit.of("    "),
  ];
  return (
    <>
      <div className="flex flex-row mb-2">
        <span className="border rounded grow p-2 mr-2 font-mono">
            {filePath === "" || filePath === undefined ? "Add a file to modify on the left." : filePath}
        </span>
      </div>

      {(hideMerge || hideMerge === undefined) ? (
        <CodeMirror
          value={file}
          extensions={extensions}
          onChange={onChange}
          theme={vscodeDark}
          style={{ overflow: "auto" }}
          placeholder={placeholderText}
        />
      ) : (
        <CodeMirrorMerge theme={vscodeDark} style={{ overflow: "auto" }}>
          <Original
            value={oldFile}
            extensions={extensions}
            onChange={onOldChange}
            placeholder={placeholderText}
          />
          <Modified value={file} extensions={extensions} onChange={onChange} placeholder={placeholderText}/>
        </CodeMirrorMerge>
      )}
    </>
  );
};

export default FileSelector;
export { getLanguage };
