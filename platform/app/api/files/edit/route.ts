import { NextRequest } from "next/server"
import { promises as fs } from 'fs';
import path from 'path';

interface Body {
    repo: string
    filePath: string
    newContent: string
}

export async function POST(request: NextRequest) {
    const body = await request.json() as Body;
    const { repo, filePath, newContent } = body;

    const dataDir = repo.startsWith("/") ? repo : path.join(process.cwd(), repo)
    console.log(dataDir)


    try {
        await fs.mkdir(dataDir, { recursive: true });
        const fullPath = path.join(dataDir, filePath);
        await fs.access(fullPath)
        await fs.writeFile(fullPath, newContent);
        return Response.json({
            success: true,
            message: 'File updated successfully'
        });
    } catch (error) {
        console.error(error);
        return Response.json({
            success: false,
            message: 'File update failed with error ' + error.message
        });
    }
}
