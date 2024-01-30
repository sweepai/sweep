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
  console.log("inside post", body);
  const command = `cd ${repo} && export FILE_PATH=${filePath} && ${script}`;
  try {
    const { stdout, stderr } = await exec(command);
    console.log("stdout:", stdout);
    console.log("stderr:", stderr);
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
