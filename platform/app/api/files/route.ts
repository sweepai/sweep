import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

interface Body {
  repo: string;
  filePath: string;
  newContent: string;
}

export async function GET(request: NextRequest) {
  const filePath = (await request.nextUrl.searchParams.get(
    "filePath",
  )) as string;
  const repo = (await request.nextUrl.searchParams.get("repo")) as string;

  const dataDir = repo.startsWith("/") ? repo : path.join(process.cwd(), repo);
  console.log(dataDir);

  try {
    const fullPath = path.join(dataDir, filePath);
    await fs.access(fullPath);
    const contents = await fs.readFile(fullPath, { encoding: "utf-8" });
    return NextResponse.json({
      contents,
      success: true,
      message: "File updated successfully",
    });
  } catch (error: any) {
    console.error(error);
    return NextResponse.json({
      success: false,
      message: "File update failed with error " + error.message,
    });
  }
}

export async function POST(request: NextRequest) {
  const body = (await request.json()) as Body;
  const { repo, filePath, newContent } = body;

  const dataDir = repo.startsWith("/") ? repo : path.join(process.cwd(), repo);
  console.log(dataDir);

  try {
    await fs.mkdir(dataDir, { recursive: true });
    const fullPath = path.join(dataDir, filePath);
    await fs.access(fullPath);
    await fs.writeFile(fullPath, newContent);
    return NextResponse.json({
      success: true,
      message: "File updated successfully",
    });
  } catch (error: any) {
    console.error(error);
    return NextResponse.json({
      success: false,
      message: "File update failed with error " + error.message,
    });
  }
}
