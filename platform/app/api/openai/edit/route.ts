import { NextRequest, NextResponse } from "next/server"
import OpenAI from 'openai';


interface Body {
    fileContents: string
    prompt: string
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

You may write one or multiple diff hunks. The MODIFIED can be empty.`

const userMessagePrompt = `Your job is to modify the current code file in order to complete the user's request:
<user_request>
{prompt}
</user_request>

Here are the file's current contents:
<file_contents>
{fileContents}
</file_contents>`

const diffRegex = /<<<<<<< ORIGINAL(\n*?)(?<oldCode>.*?)(\n*?)=======(\n*?)(?<newCode>.*?)(\n*?)>>>>>>> MODIFIED/gs

// const countNumOccurences = (needle: string, haystack: string) => {
//     if (needle === '') return 0;

//     let count = 0;
//     let pos = haystack.indexOf(needle);

//     while (pos !== -1) {
//         count++;
//         pos = haystack.indexOf(needle, pos + 1);
//     }

//     return count;
// }

// const findMaximalSuffixMatch = (needle: string, haystack: string) => {
//     const lines = needle.split("\n")
//     for (var i = 0; i < lines.length; i += 1) {
//         const substring = lines.slice(i).join("\n");
//         if (countNumOccurences(substring, haystack) === 1) {
//             return substring;
//         }
//     }
//     return "";
// }


// const appendUnitTests = (oldCode: string, searchCode: string, appendCode: string) => {
//     const maximalMatch = findMaximalSuffixMatch(searchCode, oldCode);
//     return oldCode.replace(maximalMatch, maximalMatch + '\n\n' + appendCode);
// }

export const parseRegexFromOpenAI = (response: string, fileContents: string) => {
    // console.log("file contents:\n", fileContents, "\n")
    console.log("response:\n", response, "\nend of response\n")
    const diffMatches: any = response.matchAll(diffRegex)!;
    if (!diffMatches) {
        return "";
    }
    var currentFileContents = fileContents;
    for (const diffMatch of diffMatches) {
        const oldCode = diffMatch.groups!.oldCode;
        const newCode = diffMatch.groups!.newCode;
        // console.log("old code", oldCode, "\n")
        // console.log("new code", newCode, "\n")
        currentFileContents = currentFileContents.replace(oldCode, newCode)
    }
    //console.log("current file contents:\n", currentFileContents, "\n")
    return currentFileContents
}

const callOpenAI = async (prompt: string, fileContents: string) => {
    const params: OpenAI.Chat.ChatCompletionCreateParams = {
        messages: [
            { role: 'user', content: systemMessagePrompt},
            { role: 'system', content: userMessagePrompt.replace('{prompt}', prompt).replace('{fileContents}', fileContents) }
        ],
        model: 'gpt-4-1106-preview',
    };
    const chatCompletion: OpenAI.Chat.ChatCompletion = await openai.chat.completions.create(params);
    const response = chatCompletion.choices[0].message.content!;
    return parseRegexFromOpenAI(response, fileContents);
}

export async function POST(request: NextRequest) {
    if (openai.apiKey === "") {
        const response = NextResponse.json({message: "OpenAI API key not set, ensure you have set the OPENAI_API_KEY environment variable"}, {status: 401})
        return response
    }
    const body = await request.json() as Body;
    console.log("body after being extracted in post request:", body)
    const response = await callOpenAI(body.prompt, body.fileContents);

    return NextResponse.json({
        newFileContents: response    
    })
}
