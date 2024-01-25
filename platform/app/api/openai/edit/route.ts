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
The new code block to replace the second code block. Ensure the indentation and synatx is valid.
>>>>>>> MODIFIED
\`\`\`

You may write one or multiple diff hunks. The MODIFIED can be empty.`

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

const diffRegex = /<<<<<<< ORIGINAL(\n*?)(?<oldCode>.*?)(\n*?)=======(\n*?)(?<newCode>.*?)(\n*?)>>>>>>> MODIFIED/gs

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
    console.log("file contents:\n", fileContents, "\n")
    console.log("response:\n", response, "\nend of response\n")
    const diffMatches: any = response.matchAll(diffRegex)!;
    if (!diffMatches) {
        return "";
    }
    var currentFileContents = fileContents;
    let it = 0
    for (const diffMatch of diffMatches) {
        it += 1
        const oldCode = diffMatch.groups!.oldCode;
        const newCode = diffMatch.groups!.newCode;
        console.log("old code", oldCode, "\n")
        console.log("new code", newCode, "\n")
        currentFileContents = currentFileContents.replace(oldCode, newCode)
        // if (it < 3) {
        //     console.log("current file contents:\n", currentFileContents, "\n")
        // }
    }
    return currentFileContents
}

export async function POST(request: NextRequest) {
    const body = await request.json() as Body;
    console.log("body after being extracted in post request:", body)
    const response = await callOpenAI(body.prompt, body.fileContents);
    // console.log(response)

    return NextResponse.json({
        newFileContents: response    
    })
}

// const mockResponse = String.raw`<<<<<<< ORIGINAL
// from loguru import logger
// =======
// >>>>>>> MODIFIED

// <<<<<<< ORIGINAL
//                 logger.error(f"Error deleting comment: {e}")
// =======
// >>>>>>> MODIFIED`

// const mockFileContents = String.raw`import hashlib
// import time

// from github.Repository import Repository
// from loguru import logger

// from sweepai.config.client import (
//     RESET_FILE,
//     REVERT_CHANGED_FILES_TITLE,
//     RULES_LABEL,
//     RULES_TITLE,
//     get_blocked_dirs,
// )
// from sweepai.config.server import MONGODB_URI
// from sweepai.core.post_merge import PostMerge
// from sweepai.events import IssueCommentRequest
// from sweepai.handlers.on_merge import comparison_to_diff
// from sweepai.handlers.stack_pr import stack_pr
// from sweepai.utils.buttons import ButtonList, check_button_title_match
// from sweepai.utils.chat_logger import ChatLogger
// from sweepai.utils.event_logger import posthog
// from sweepai.utils.github_utils import get_github_client
// from sweepai.utils.str_utils import BOT_SUFFIX


// def handle_button_click(request_dict):
//     request = IssueCommentRequest(**request_dict)
//     user_token, gh_client = get_github_client(request_dict["installation"]["id"])
//     button_list = ButtonList.deserialize(request_dict["comment"]["body"])
//     selected_buttons = [button.label for button in button_list.get_clicked_buttons()]
//     repo = gh_client.get_repo(
//         request_dict["repository"]["full_name"]
//     )  # do this after checking ref
//     comment_id = request.comment.id
//     pr = repo.get_pull(request_dict["issue"]["number"])
//     comment = pr.get_issue_comment(comment_id)
//     if check_button_title_match(
//         REVERT_CHANGED_FILES_TITLE, request.comment.body, request.changes
//     ):
//         revert_files = []
//         for button_text in selected_buttons:
//             revert_files.append(button_text.split(f"{RESET_FILE} ")[-1].strip())
//         handle_revert(file_paths=revert_files, pr_number=request_dict["issue"]["number"], repo=repo)
//         comment.edit(
//             ButtonList(
//                 buttons=[
//                     button
//                     for button in button_list.buttons
//                     if button.label not in selected_buttons
//                 ],
//                 title=REVERT_CHANGED_FILES_TITLE,
//             ).serialize()
//         )

//     if check_button_title_match(RULES_TITLE, request.comment.body, request.changes):
//         rules = []
//         for button_text in selected_buttons:
//             rules.append(button_text.split(f"{RULES_LABEL} ")[-1].strip())
//         handle_rules(request_dict=request_dict, rules=rules, user_token=user_token, repo=repo, gh_client=gh_client)
//         comment.edit(
//     ButtonList(
//                 buttons=[
//                     button
//                     for button in button_list.buttons
//                     if button.label not in selected_buttons
//                 ],
//                 title=RULES_TITLE,
//             ).serialize()
//             + BOT_SUFFIX
//         )
//         if not rules:
//             try:
//                 comment.delete()
//             except Exception as e:
//                 logger.error(f"Error deleting comment: {e}")


// def handle_revert(file_paths, pr_number, repo: Repository):
//     pr = repo.get_pull(pr_number)
//     branch_name = pr.head.ref if pr_number else pr.pr_head

//     def get_contents_with_fallback(
//         repo: Repository, file_path: str, branch: str = None
//     ):
//         try:
//             if branch:
//                 return repo.get_contents(file_path, ref=branch)
//             return repo.get_contents(file_path)
//         except Exception:
//             return None

//     old_file_contents = [
//         get_contents_with_fallback(repo, file_path) for file_path in file_paths
//     ]
//     for file_path, old_file_content in zip(file_paths, old_file_contents):
//         try:
//             current_content = repo.get_contents(file_path, ref=branch_name)
//             if old_file_content:
//                 repo.update_file(
//                     file_path,
//                     f"Revert {file_path}",
//                     old_file_content.decoded_content,
//                     sha=current_content.sha,
//                     branch=branch_name,
//                 )
//             else:
//                 repo.delete_file(
//                     file_path,
//                     f"Delete {file_path}",
//                     sha=current_content.sha,
//                     branch=branch_name,
//                 )
//         except Exception:
//             pass  # file may not exist and this is expected


// def handle_rules(request_dict, rules, user_token, repo: Repository, gh_client):
//     pr = repo.get_pull(request_dict["issue"]["number"])
//     chat_logger = (
//         ChatLogger(
//             {"username": request_dict["sender"]["login"]},
//         )
//         if MONGODB_URI
//         else None
//     )
//     blocked_dirs = get_blocked_dirs(repo)
//     comparison = repo.compare(pr.base.sha, pr.head.sha)  # head is the most recent
//     commits_diff = comparison_to_diff(comparison, blocked_dirs)
//     for rule in rules:
//         changes_required, issue_title, issue_description = PostMerge(
//             chat_logger=chat_logger
//         ).check_for_issues(rule=rule, diff=commits_diff)
//         tracking_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:10]
//         if changes_required:
//             new_pr = stack_pr(
//                 request=issue_description
//                 + "\n\nThis issue was created to address the following rule:\n"
//                 + rule,
//                 pr_number=request_dict["issue"]["number"],
//                 username=request_dict["sender"]["login"],
//                 repo_full_name=request_dict["repository"]["full_name"],
//                 installation_id=request_dict["installation"]["id"],
//                 tracking_id=tracking_id,
//             )
//             posthog.capture(request_dict["sender"]["login"], "rule_pr_created")
// `