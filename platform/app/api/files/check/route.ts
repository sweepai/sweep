import { NextRequest } from "next/server";
import { checkCode } from "@/lib/tree";

interface Body {
  sourceCode: string;
  fileContents: string;
}

export async function GET(request: NextRequest) {
  const sourceCode = (await request.nextUrl.searchParams.get("sourceCode")) as string;
  const filePath = (await request.nextUrl.searchParams.get(
    "filePath",
  )) as string;

  return new Response(checkCode(sourceCode, filePath));
}
