import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { OpenAIStream, StreamingTextResponse } from "ai";
import { Snippet } from "../../../../lib/search";
import { Message } from "@/lib/types";
import { ChatCompletionMessageParam } from "openai/resources/chat/completions.mjs";

interface Body {
  fileContents: string;
  prompt: string;
  snippets: Snippet[];
  userMessage: string;
  additionalMessages?: Message[];
  systemMessage: string;
}

const systemMessagePromptCreate = `You are creating a file of code in order to solve a user's request. You will follow the request under "# Request" and respond based on the format under "# Format".

# Request

file_name: filename will be here

Instructions will be here

# Format

You MUST respond in the following XML format:

<new_file>
The contents of the new file. NEVER write comments. All functions and classes will be fully implemented.
When writing unit tests, they will be complete, extensive, and cover ALL edge cases. You will make up data for unit tests. Create mocks when necessary.
</new_file>`;

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY || "", // This is the default and can be omitted
});

export async function POST(request: NextRequest) {
  if (openai.apiKey === "") {
    const response = NextResponse.json(
      {
        message:
          "OpenAI API key not set, ensure you have set the OPENAI_API_KEY environment variable",
      },
      { status: 401 },
    );
    return response;
  }
  const body = (await request.json()) as Body;

  if (
    body.snippets.map((snippet) => snippet.content).join("").length >
    128000 * 3
  ) {
    const response = NextResponse.json(
      {
        message:
          "Input is too large, ran out of tokens, remove some read-only files.",
      },
      { status: 400 },
    );
    return response;
  }
  const messages: ChatCompletionMessageParam[] = [
    { role: "system", content: systemMessagePromptCreate },
    ...(body.additionalMessages || []),
    { role: "user", content: body.userMessage },
  ];

  const params: OpenAI.Chat.ChatCompletionCreateParams = {
    messages,
    model: "gpt-4-1106-preview",
    stream: true,
  };
  console.log("params", params);
  const response = await openai.chat.completions.create(params);
  const stream = OpenAIStream(response);
  return new StreamingTextResponse(stream);
}
