import { NextRequest } from "next/server"
import { promises as fs, Dirent } from "fs";
import path from "path";


interface Body {
    repo: string
}

const blockedPaths = [
    ".git",
    "node_modules",
    "venv",
    "__pycache__",
    ".next",
    "cache"
]


export async function POST(request: NextRequest) {
    // Body -> { stdout: string, stderr: string, code: number}
    const body = await request.json() as Body;
    const { repo } = body;

    async function listNonBinaryFilesBFS(rootDir: string, fileLimit: number = 5000): Promise<string[]> {
        let queue: string[] = [rootDir];
        let nonBinaryFiles: string[] = [];

        while (queue.length > 0 && nonBinaryFiles.length < fileLimit) {
            const currentDir = queue.shift()!;
            if (blockedPaths.some(blockedPath => currentDir.includes(blockedPath))) {
                continue;
            }
            const items: Dirent[] = await fs.readdir(currentDir, { withFileTypes: true });

            for (const item of items) {
                const res: string = path.resolve(currentDir, item.name);
                if (item.isDirectory()) {
                    queue.push(res);
                } else if (item.isFile()) {
                    try {
                        const content: Buffer = await fs.readFile(res);
                        if (!content.includes(0) && nonBinaryFiles.length < fileLimit) {
                            nonBinaryFiles.push(res.slice(rootDir.length + 1));
                        }
                    } catch (readError) {
                        console.error(`Error reading file ${res}: ${readError}`);
                    }
                }
            }
        }

        return nonBinaryFiles;
    }

    try {
        const nonBinaryFiles = await listNonBinaryFilesBFS(repo);
        return new Response(JSON.stringify(nonBinaryFiles), { status: 200 });
    } catch (error: any) {
        return new Response(error.message, { status: 500 });
    }
}
