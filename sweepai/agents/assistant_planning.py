import copy
import re
import traceback
import uuid
from pathlib import Path

from loguru import logger

from sweepai.agents.assistant_wrapper import (
    client,
    openai_assistant_call,
    run_until_complete,
)
from sweepai.core.entities import AssistantRaisedException, FileChangeRequest, Message
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.progress import AssistantConversation, TicketProgress

system_message = r""" You are searching through a codebase to guide a junior developer on how to solve the user request. The junior developer will follow your instructions exactly and make the changes.

# User Request
{user_request}

# Guide
## Step 1: Unzip the file into /mnt/data/repo. Then list all root level directories. You must copy the below code verbatim into the file.
```python
import zipfile
import os

zip_path = '{file_path}'
extract_to_path = 'mnt/data/repo'
os.makedirs(extract_to_path, exist_ok=True)
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_to_path)
    zip_contents = zip_ref.namelist()
    root_dirs = {{name.split('/')[0] for name in zip_contents}}
    print(f'Root directories: {{root_dirs}}')
```

## Step 2: Find the relevant files.
You can search by file name or by keyword search in the contents.

## Step 3: Find relevant lines.
1. Locate the lines of code that contain the identified keywords or are at the specified line number. You can use keyword search or manually look through the file 100 lines at a time.
2. Check the surrounding lines to establish the full context of the code block.
3. Adjust the starting line to include the entire functionality that needs to be refactored or moved.
4. Finally determine the exact line spans that include a logical and complete section of code to be edited.

```python
def print_lines_with_keyword(content, keywords):
    max_matches=5
    context = 10

    matches = [i for i, line in enumerate(content.splitlines()) if any(keyword in line.lower() for keyword in keywords)]
    print(f"Found {{len(matches)}} matches, but capping at {{max_match}}")
    matches = matches[:max_matches]
    expanded_matches = set()

    for match in matches:
        start = max(0, match - context)
        end = min(len(content.splitlines()), match + context + 1)
        for i in range(start, end):
            expanded_matches.add(i)

    for i in sorted(expanded_matches):
        print(f"{{i}}: {{content.splitlines()[i]}}")
```

## Step 4: Construct a plan.
Provide the final plan to solve the issue, following these rules:
* DO NOT apply any changes here, they will not be persisted. You must provide the plan and the developer will apply the changes.
* You may only create new files and modify existing files.
* File paths should be relative paths from the root of the repo.
* Use the minimum number of create and modify operations required to solve the issue.
* Start and end lines indicate the exact start and end lines to edit. Expand this to encompass more lines if you're unsure where to make the exact edit.

Respond in the following format:

```xml
<plan>
<create_file file="file_path_1">
* Natural language instructions for creating the new file needed to solve the issue.
* Reference necessary files, imports and entity names.
...
</create_file>
...

<modify_file file="file_path_2" start_line="i" end_line="j">
* Natural language instructions for the modifications needed to solve the issue.
* Be concise and reference necessary files, imports and entity names.
...
</modify_file>
...

</plan>
```"""


@file_cache(ignore_params=["zip_path", "chat_logger", "ticket_progress"])
def new_planning(
    request: str,
    zip_path: str,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = None,
    ticket_progress: TicketProgress | None = None,
) -> list[FileChangeRequest]:
    planning_iterations = 3
    try:

        def save_ticket_progress(assistant_id: str, thread_id: str, run_id: str):
            assistant_conversation = AssistantConversation.from_ids(
                assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
            )
            if not assistant_conversation:
                return
            ticket_progress.planning_progress.assistant_conversation = (
                assistant_conversation
            )
            ticket_progress.save()

        logger.info("Uploading file...")
        zip_file_object = client.files.create(file=Path(zip_path), purpose="assistants")
        logger.info("Done uploading file.")
        zip_file_id = zip_file_object.id
        response = openai_assistant_call(
            request=request,
            assistant_id=assistant_id,
            additional_messages=additional_messages,
            uploaded_file_ids=[zip_file_id],
            chat_logger=chat_logger,
            save_ticket_progress=save_ticket_progress
            if ticket_progress is not None
            else None,
            instructions=system_message.format(
                user_request=request, file_path=f"mnt/data/{zip_file_id}"
            ),
        )
        run_id = response.run_id
        thread_id = response.thread_id
        for _ in range(planning_iterations):
            save_ticket_progress(
                assistant_id=response.assistant_id,
                thread_id=response.thread_id,
                run_id=response.run_id,
            )
            messages = response.messages
            final_message = messages.data[0].content[0].text.value
            fcrs = []
            fcr_matches = list(
                re.finditer(FileChangeRequest._regex, final_message, re.DOTALL)
            )
            if len(fcr_matches) > 0:
                break
            else:
                client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content="A valid plan (within the <plan> tags) was not provided. Please continue working on the plan. If you are stuck, consider starting over.",
                )
                run = client.beta.threads.runs.create(
                    thread_id=response.thread_id,
                    assistant_id=response.assistant_id,
                    instructions=system_message.format(
                        user_request=request, file_path=f"mnt/data/{zip_file_id}"
                    ),
                )
                run_id = run.id
                messages = run_until_complete(
                    thread_id=thread_id,
                    run_id=run_id,
                    assistant_id=response.assistant_id,
                )
        for match_ in fcr_matches:
            group_dict = match_.groupdict()
            if group_dict["change_type"] == "create_file":
                group_dict["change_type"] = "create"
            if group_dict["change_type"] == "modify_file":
                group_dict["change_type"] = "modify"
            fcr = FileChangeRequest(**group_dict)
            fcr.filename = fcr.filename.lstrip("/")
            fcr.instructions = fcr.instructions.replace("\n*", "\n•")
            fcr.instructions = fcr.instructions.strip("\n")
            if fcr.instructions.startswith("*"):
                fcr.instructions = "•" + fcr.instructions[1:]
            fcrs.append(fcr)
            new_file_change_request = copy.deepcopy(fcr)
            new_file_change_request.change_type = "check"
            new_file_change_request.parent = fcr
            new_file_change_request.id_ = str(uuid.uuid4())
            fcrs.append(new_file_change_request)
        assert len(fcrs) > 0
        return fcrs
    except AssistantRaisedException as e:
        raise e
    except Exception as e:
        logger.exception(e)
        if chat_logger is not None:
            discord_log_error(
                str(e)
                + "\n\n"
                + traceback.format_exc()
                + "\n\n"
                + str(chat_logger.data)
            )
        return None


if __name__ == "__main__":
    request = """## Title: replace the broken tutorial link in installation.md with https://docs.sweep.dev/usage/tutorial\n"""
    additional_messages = [
        Message(
            role="user",
            content='<relevant_snippets_in_repo>\n<snippet source="docs/pages/usage/tutorial.mdx:45-60">\n...\n45: Now to be a Sweep power user, check out [Advanced: becoming a Sweep power user](https://docs.sweep.dev/usage/advanced).\n</snippet>\n<snippet source="docs/pages/usage/tutorial.mdx:30-45">\n...\n30: \n31: ![PR Comment](/tutorial/comment.png)\n32: \n33:     c. If you have GitHub Actions set up, it will automatically run the linters, build, and tests and will show any failed logs to Sweep to handle. This only works with GitHub Actions and not other CI providers, so unfortunately for Vercel we have to copy paste manually.\n34: \n35: ![GitHub Actions](/tutorial/github_actions.png)\n36: \n37: 6. Once you are happy with the PR, you can merge it and it will be deployed to production via Vercel.\n38: \n39: \n40: ![Final](/tutorial/final.png)\n41: \n42: \n43: You can see the final example at https://github.com/kevinlu1248/docusaurus-2/pull/4 with preview https://docusaurus-2-ql4cskc5o-sweepai.vercel.app/.\n44: \n45: Now to be a Sweep power user, check out [Advanced: becoming a Sweep power user](https://docs.sweep.dev/usage/advanced).\n...\n</snippet>\n<snippet source="docs/installation.md:45-60">\n...\n45: * Provide any additional context that might be helpful, e.g. see "src/App.test.tsx" for an example of a good unit test.\n46: * For more guidance, visit [Advanced](https://docs.sweep.dev/usage/advanced), or watch the following video.\n47: \n48: [![Video](http://img.youtube.com/vi/Qn9vB71R4UM/0.jpg)](http://www.youtube.com/watch?v=Qn9vB71R4UM "Advanced Sweep Tricks and Feedback Tips")\n49: \n50: For configuring Sweep for your repo, see [Config](https://docs.sweep.dev/usage/config), especially for setting up Sweep Rules and Sweep Sweep.\n51: \n52: ## Limitations of Sweep (for now) ⚠️\n53: \n54: * 🗃️ **Gigantic repos**: >5000 files. We have default extensions and directories to exclude but sometimes this doesn\'t catch them all. You may need to block some directories (see [`blocked_dirs`](https://docs.sweep.dev/usage/config#blocked_dirs))\n55:     * If Sweep is stuck at 0% for over 30 min and your repo has a few thousand files, let us know.\n56: \n57: * 🏗️ **Large-scale refactors**: >5 files or >300 lines of code changes (we\'re working on this!)\n58:     * We can\'t do this - "Refactor entire codebase from Tensorflow to PyTorch"\n59: \n60: * 🖼️ **Editing images** and other non-text assets\n...\n</snippet>\n<snippet source="docs/pages/usage/tutorial.mdx:0-15">\n0: # Tutorial for Getting Started with Sweep\n1: \n2: We recommend using an existing **real project** for Sweep, but if you must start from scratch, we recommend **using a template**. In particular, we recommend Vercel templates and Vercel auto-deploy, since Vercel\'s auto-generated previews make it **easy to review Sweep\'s PRs**\n3: \n4: We\'ll use [Docusaurus](https://vercel.com/templates/next.js/docusaurus-2) since it\'s is the easiest to set up (no backend). To see other templates see https://vercel.com/templates.\n5: \n6: 1. Go to https://vercel.com/templates/next.js/docusaurus-2 (or another template) and click "Deploy".\n7: \n8: ![Deploy](/tutorial/deployment.png)\n9: \n10: 2. Vercel will prompt you to select a GitHub account and click "Clone" after. This will trigger a build and deploy which will take a few minutes. Once the build is done, you will be greeted with a congratulations message.\n11: \n12: ![Congratulations](/tutorial/congratulations.png)\n13: \n14: 3. Go to the [Sweep Installation](https://github.com/apps/sweep-ai) page and click the grey "Configure" button or the green "Install" button. Ensure that that the Vercel template (i.e. Docusaurus) is configured to use Sweep.\n...\n</snippet>\n</relevant_snippets_in_repo>\ndocs/\n  installation.md\n  docs/pages/\n    docs/pages/usage/\n      _meta.json\n      advanced.mdx\n      config.mdx\n      extra-self-host.mdx\n      sandbox.mdx\n      tutorial.mdx',
            name=None,
            function_call=None,
            key=None,
        )
    ]
    print(
        new_planning(
            request,
            "/tmp/sweep_archive.zip",
            chat_logger=ChatLogger(
                {"username": "kevinlu1248", "title": "Unit test for planning"}
            ),
            ticket_progress=TicketProgress(tracking_id="ed47605a38"),
        )
    )
