import { NextRequest } from "next/server"
import { promises as fs, Dirent } from "fs";
import path from "path";


interface Body {
    repo: string
}

export async function POST(request: NextRequest) {
    // Body -> { stdout: string, stderr: string, code: number}
    const body = await request.json() as Body;
    const { repo } = body;
    async function listNonBinaryFiles(dir: string): Promise<string[]> {
        let nonBinaryFiles: string[] = [];
        const files: Dirent[] = await fs.readdir(dir, { withFileTypes: true });
        for (const file of files) {
            const res: string = path.resolve(dir, file.name);
            if (file.isDirectory()) {
                nonBinaryFiles = nonBinaryFiles.concat(await listNonBinaryFiles(res));
            } else {
                const content: Buffer = await fs.readFile(res);
                if (!content.includes(0)) {
                    nonBinaryFiles.push(res);
                }
            }
        }
        return nonBinaryFiles;
    }

    try {
        const nonBinaryFiles = await listNonBinaryFiles(repo);
        return new Response(JSON.stringify(nonBinaryFiles), { status: 200 });
    } catch (error: any) {
        return new Response(error.message, { status: 500 });
    }
}
