import { Dirent, promises as fs } from "fs";
import { File, Snippet } from "./types";
// import { cache } from 'react'

import path from "path";
import Fuse from "fuse.js";

const blockedPaths = [
  ".git",
  "node_modules",
  "venv",
  "__pycache__",
  ".next",
  "cache",
  "benchmark",
  "logn_logs",
];

const limit = 1000;

function splitIntoChunks(text: string, metadata?: Partial<Snippet>) {
  if (text === "") return [];

  const lines = text.split("\n");
  const chunkSize = 40;
  const overlap = 10;
  let chunks: Snippet[] = [];

  for (let i = 0; i < lines.length; i += chunkSize - (i > 0 ? overlap : 0)) {
    chunks.push({
      file: "",
      start: i,
      end: Math.min(i + chunkSize, lines.length),
      entireFile: text,
      content: lines.slice(i, i + chunkSize).join("\n"),
      ...(metadata || {}),
    });
  }

  return chunks;
}

const listFiles = async (
  rootDir: string,
  fileLimit: number = limit,
): Promise<File[]> => {
  let queue: string[] = [rootDir];
  let files: File[] = [];

  while (queue.length > 0 && files.length < fileLimit) {
    const currentDir = queue.shift()!;
    if (blockedPaths.some((blockedPath) => currentDir.includes(blockedPath))) {
      continue;
    }
    const items: Dirent[] = await fs.readdir(currentDir, {
      withFileTypes: true,
    });

    for (const item of items) {
      const res: string = path.resolve(currentDir, item.name);
      if (item.isDirectory()) {
        queue.push(res);
      } else if (item.isFile()) {
        try {
          const content: Buffer = await fs.readFile(res);
          if (!content.includes(0) && files.length < fileLimit) {
            files.push({
              name: res,
              path: res.slice(rootDir.length + 1),
              isDirectory: false,
              content: content.toString(),
              snippets: splitIntoChunks(content.toString(), {
                file: res,
              }),
            });
          }
        } catch (readError) {
          console.error(`Error reading file ${res}: ${readError}`);
        }
      }
    }
  }

  return files;
};

const getIndex = async (
  rootDir: string,
  fileLimit: number = limit,
): Promise<Fuse<Snippet>> => {
  const files = await listFiles(rootDir, fileLimit);
  const chunks = files.flatMap((file) => file.snippets ?? []);
  const fuse = new Fuse(chunks, {
    keys: ["content"],
    includeScore: true,
    threshold: 0.3,
  });
  return fuse;
};

const searchFiles = async (
  rootDir: string,
  query: string,
  fileLimit: number = limit,
  searchLimit: number = limit,
): Promise<Snippet[]> => {
  const fuse = await getIndex(rootDir, fileLimit);
  return fuse
    .search(query, {
      limit: searchLimit,
    })
    .map((result) => result.item);
};

export { splitIntoChunks, listFiles, searchFiles };
export type { File, Snippet };
