import { NextRequest, NextResponse } from "next/server";
import { promises as fs, Dirent } from "fs";
import { minimatch } from "minimatch";
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
  ): Promise<string[]> {
    let queue: string[] = [rootDir];
    let nonBinaryFiles: string[] = [];

    while (
      queue.length > 0 &&
      fileLimit > 0 &&
      nonBinaryFiles.length < fileLimit
    ) {
      const currentDir = queue.shift()!;
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
        } else if (item.isFile()) {
          try {
            const content: Buffer = await fs.readFile(res);
            if (
              !content.includes(0) &&
              fileLimit > 0 &&
              nonBinaryFiles.length < fileLimit
            ) {
              nonBinaryFiles.push(res.slice(rootDir.length + 1));
            }
          } catch (readError) {
            console.error(`Error reading file ${res}: ${readError}`);
          }
        }
      }
    }
    console.log("here files", nonBinaryFiles);

    return nonBinaryFiles;
  }

  try {
    const stats = await fs.stat(repo);
    if (!stats.isDirectory()) {
      return new NextResponse("Not a directory", { status: 400 });
    }
    const nonBinaryFiles = await listNonBinaryFilesBFS(repo);
    console.log("nonBinaryFiles", nonBinaryFiles);
    return new NextResponse(JSON.stringify(nonBinaryFiles), { status: 200 });
  } catch (error: any) {
    return new NextResponse(error.message, { status: 500 });
  }
}
