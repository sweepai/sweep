import { NextRequest } from "next/server"
import { promisify } from 'util';
import { exec as execCallback } from 'child_process';

const exec = promisify(execCallback);


interface Body {
    repo: string
    branch: string
}

export async function POST(request: NextRequest) {
    const body = await request.json() as Body;
    const { repo, branch } = body;
    const command = `cd ${repo} git checkout ${branch} && git checkout -b ${branch}`;
    try {
        const { stdout, stderr } = await exec(command);
        console.log('stdout:', stdout);
        console.log('stderr:', stderr);
        return Response.json({
            stdout,
            stderr,
            code: 0
        })
    } catch (error: any) {
        return Response.json({
            stdout: error.stdout,
            stderr: error.stderr,
            code: error.code
        })
    }
}
