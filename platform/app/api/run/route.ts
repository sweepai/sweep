import { NextRequest, NextResponse } from "next/server";
import { promisify } from "util";
import { exec as execCallback } from "child_process";

const exec = promisify(execCallback);

interface Body {
  repo: string;
  filePath: string;
  script: string;
}

export async function POST(request: NextRequest) {
  // Body -> { stdout: string, stderr: string, code: number}
  const body = (await request.json()) as Body;
  const { repo, filePath, script } = body;
  let command = `cd ${repo} && export FILE_PATH=${filePath}`;
  if (script) {
    // optional script
    command += ` && ${script}`;
  }
  try {
    const { stdout, stderr } = await exec(command);
    return NextResponse.json({
      stdout,
      stderr,
      code: 0,
    });
  } catch (error: any) {
    return NextResponse.json({
      stdout: error.stdout,
      stderr: error.stderr,
      code: error.code,
    });
  }
}
