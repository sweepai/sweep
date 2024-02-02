import { NextRequest, NextResponse } from "next/server";
import { promises as fs, Dirent } from "fs";
import path from "path";

interface Body {
  repo: string;
  limit: number;
  blockedGlobs: string[];
}

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

export async function POST(request: NextRequest) {
  // Body -> { stdout: string, stderr: string, code: number}
  const body = (await request.json()) as Body;
  const { repo, blockedGlobs = [], limit = 10000 } = body;

  async function listNonBinaryFilesBFS(
    rootDir: string,
    fileLimit: number = limit,
  ): Promise<[{ path: string; lastModified: number }[], string[]]> {
    let queue: string[] = [rootDir];
    let nonBinaryFiles: { path: string; lastModified: number }[] = [];
    let directories: Set<string> = new Set([rootDir]);
    while (
      queue.length > 0 &&
      fileLimit > 0 &&
      nonBinaryFiles.length < fileLimit
    ) {
      const currentDir = queue.shift()!;
      directories.add(currentDir);
      // if (blockedGlobs.some(blockedGlob => minimatch(currentDir, blockedGlob))) {
      if (
        blockedGlobs.some((blockedGlob) => currentDir.includes(blockedGlob))
      ) {
        continue;
      }
      const items: Dirent[] = await fs.readdir(currentDir, {
        withFileTypes: true,
      });

      for (const item of items) {
        const res: string = path.resolve(currentDir, item.name);
        if (item.isDirectory()) {
          queue.push(res);
          directories.add(res);
        } else if (item.isFile()) {
          try {
            const content: Buffer = await fs.readFile(res);
            if (
              !content.includes(0) &&
              fileLimit > 0 &&
              nonBinaryFiles.length < fileLimit
            ) {
              const { mtimeMs } = await fs.stat(res);
              nonBinaryFiles.push({
                path: res.slice(rootDir.length + 1),
                lastModified: mtimeMs,
              });
            }
          } catch (readError) {
            console.error(`Error reading file ${res}: ${readError}`);
          }
        }
      }
    }

    return [nonBinaryFiles.sort((a, b) => b.lastModified - a.lastModified), Array.from(directories)];
  }

  try {
    const stats = await fs.stat(repo);
    if (!stats.isDirectory()) {
      return new NextResponse("Not a directory", { status: 400 });
    }
    const [filesWithMeta, directories ] = await listNonBinaryFilesBFS(repo);
    const sortedFiles = filesWithMeta.map((fileMeta) => fileMeta.path);
    return new NextResponse(JSON.stringify({ sortedFiles, directories }), { status: 200 });
  } catch (error: any) {
    return new NextResponse(error.message, { status: 500 });
  }
}
