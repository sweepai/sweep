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
}

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY || "", // This is the default and can be omitted
});

const systemMessagePrompt = `You are a brilliant and meticulous engineer assigned to modify a code file. When you write code, the code works on the first try and is syntactically perfect. You have the utmost care for the code that you write, so you do not make mistakes. Take into account the current code's language, code style and what the user is attempting to accomplish. You are to follow the instructions exactly and do nothing more. If the user requests multiple changes, you must make the changes one at a time and finish each change fully before moving onto the next change.

You MUST respond in the following diff format:

\`\`\`
<<<<<<< ORIGINAL
The first code block to replace. Ensure the indentation is valid.
=======
The new code block to replace the first code block. Ensure the indentation and syntax is valid.
>>>>>>> MODIFIED

<<<<<<< ORIGINAL
The second code block to replace. Ensure the indentation is valid.
=======
The new code block to replace the second code block. Ensure the indentation and syntax is valid.
>>>>>>> MODIFIED
\`\`\`

You may write one or multiple diff hunks. The MODIFIED can be empty.`;

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
    { role: "system", content: systemMessagePrompt },
    ...(body.additionalMessages || []),
    { role: "user", content: body.userMessage },
  ];

  const params: OpenAI.Chat.ChatCompletionCreateParams = {
    messages,
    model: "gpt-4-1106-preview",
    stream: true,
  };
  const response = await openai.chat.completions.create(params);
  const stream = OpenAIStream(response);
  return new StreamingTextResponse(stream);
}
