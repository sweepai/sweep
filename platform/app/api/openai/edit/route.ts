import { NextRequest, NextResponse } from "next/server"
import OpenAI from 'openai';



interface Body {
    fileContents: string
    prompt: string
}

const openai = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY || "", // This is the default and can be omitted
});

const systemMessagePrompt = `You are a brilliant and meticulous engineer assigned to modify a code file. When you write code, the code works on the first try and is syntactically perfect. You have the utmost care for the code that you write, so you do not make mistakes. Take into account the current code's language, code style and what the user is attempting to accomplish. You are to follow the instructions exactly and do nothing more.

You MUST respond in the following diff format:

\`\`\`
<<<<<<< ORIGINAL
The code block to replace. Ensure the indentation is valid.
=======
The new code block. Ensure the indentation is valid.
>>>>>>> MODIFIED
\`\`\``

const userMessagePrompt = `Your job is to add modify the current code file in order to complete the user's request:
<user_request>
{prompt}
</user_request>

Here are the file's current contents:
<file_contents>
{fileContents}
</file_contents>`

// const codeBlockToExtendRegex = /<code_block_to_extend>([\s\S]*)<\/code_block_to_extend>/g
// const additionalUnitTestRegex = /<new_code>([\s\S]*)$/g

const diffRegex = /<<<<<<< ORIGINAL\n(?<oldCode>.*?)\n=======\n(?<newCode>.*?)\n>>>>>>> MODIFIED/gs

const countNumOccurences = (needle: string, haystack: string) => {
    if (needle === '') return 0;

    let count = 0;
    let pos = haystack.indexOf(needle);

    while (pos !== -1) {
        count++;
        pos = haystack.indexOf(needle, pos + 1);
    }

    return count;
}

const findMaximalSuffixMatch = (needle: string, haystack: string) => {
    const lines = needle.split("\n")
    for (var i = 0; i < lines.length; i += 1) {
        const substring = lines.slice(i).join("\n");
        if (countNumOccurences(substring, haystack) === 1) {
            return substring;
        }
    }
    return "";
}


const appendUnitTests = (oldCode: string, searchCode: string, appendCode: string) => {
    // if (searchCode && appendCode) {
    //     let codeBlockToExtend = searchCode[0];
    //     codeBlockToExtend = codeBlockToExtend.split('\n').slice(2, -2).join('\n');
    //     let additionalUnitTest = appendCode[0];
    //     additionalUnitTest = additionalUnitTest.split('\n').slice(2, -2).join('\n');
    //     console.log(codeBlockToExtend)
    //     console.log(additionalUnitTest)
        const maximalMatch = findMaximalSuffixMatch(searchCode, oldCode);
        return oldCode.replace(maximalMatch, maximalMatch + '\n\n' + appendCode);
    // } else {
    //     return "";
    // }
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
    console.log("file contents", fileContents, "\n")
    console.log("response\n", response, "\nend of response\n")
    const diffMatches = response.matchAll(diffRegex)!;
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
    return currentFileContents
}

const haystack = `# ...
        print("hello world")

    def print():
        print("hello world")`

const needle = `class TestUnit():
    # ...
    
    def print():
        print("hello world")`

const codeToAppend = `print("goodbye")`

export async function POST(request: NextRequest) {
    const body = await request.json() as Body;
    console.log("body after being extracted in post request:", body)
    const response = await callOpenAI(body.prompt, body.fileContents);
    console.log(response)

    return NextResponse.json({
        newFileContents: response    
    })
}
