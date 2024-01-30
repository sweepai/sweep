import { NextRequest, NextResponse } from "next/server";
import { promisify } from "util";
import { exec as execCallback } from "child_process";

const exec = promisify(execCallback);

interface Body {
  repo: string;
  branch: string;
}

export async function GET(request: NextRequest) {
  const repo = request.nextUrl.searchParams.get("repo") as string;
  console.log(repo);

  const command = `cd ${repo} && git branch --show-current`;
  try {
    const { stdout, stderr } = await exec(command);
    console.log("stdout:", stdout);
    console.log("stderr:", stderr);
    return NextResponse.json({
      branch: stdout,
      success: true,
      message: "Branch fetched successfully",
    });
  } catch (error: any) {
    return NextResponse.json({
      branch: "",
      success: false,
      message: "Branch fetch failed with error " + error.message,
    });
  }
}

export async function POST(request: NextRequest) {
  const body = (await request.json()) as Body;
  const { repo, branch } = body;
  const command = `cd ${repo} && git checkout ${branch} && git checkout -b ${branch}`;
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
