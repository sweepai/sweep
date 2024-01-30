import { NextRequest, NextResponse } from "next/server";
import { searchFiles } from "@/lib/search";

interface Body {
  repo: string;
  query: string;
}

export async function GET(request: NextRequest) {
  const repo = (await request.nextUrl.searchParams.get("repo")) as string;
  const query = (await request.nextUrl.searchParams.get("query")) as string;

  try {
    const snippets = await searchFiles(repo, query, 1000, 5);
    return NextResponse.json({
      snippets,
      success: true,
      message: "File updated successfully",
    });
  } catch (error: any) {
    console.error(error);
    return NextResponse.json({
      snippets: [],
      success: false,
      message: "File update failed with error " + error.message,
    });
  }
}
