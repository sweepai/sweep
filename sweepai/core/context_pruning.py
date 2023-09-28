import re
from logn import logger
from sweepai.config.client import get_description
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel
from sweepai.core.prompts import (
    repo_description_prefix_prompt,
    system_message_prompt,
)
from sweepai.utils.prompt_constructor import HumanMessagePrompt

system_message_prompt = """\
Your name is Sweep bot. You are a brilliant and meticulous engineer assigned to the following Github issue. We are currently gathering the minimum set of information that allows us to plan the solution to the issue. Take into account the current repository's language, frameworks, and dependencies. It is very important that you get this right."""

pruning_prompt = """\
The above <repo_tree>, <snippets_in_repo>, and <paths_in_repo> have unnecessary information.
The snippets, and paths were fetched by a search engine, so they are noisy.
The unnecessary information will hurt your performance on this task, so prune paths_in_repo, snippets_in_repo, and repo_tree to keep only the absolutely necessary information.

First, list all of the files and directories we should keep in paths_to_keep. Be as specific as you can.
Second, list any directories that are currently closed that should be expanded.
If you list a directory, you do not need to list its subdirectories or files in its subdirectories.
Do not remove files or directories that are referenced in the issue title or descriptions.

Reply in the following format:

Analysis of current folder structure referencing the issue metadata:
* Thought about files, directories, and relevance 1 
* Thought about files, directories, and relevance 2
...

Proposal for exploration:
* Proposed directory and reason 1
* Proposed directory and reason 2
...

<paths_to_keep>
* file or directory to keep 1
* file or directory to keep 2
...
</paths_to_keep>

<directories_to_expand>
* directory to expand 1
* directory to expand 2
...
</directories_to_expand>"""


class ContextToPrune(RegexMatchableBaseModel):
    paths_to_keep: list[str] = []
    directories_to_expand: list[str] = []

    @classmethod
    def from_string(cls, string: str, **kwargs):
        paths_to_keep = []
        directories_to_expand = []
        paths_to_keep_pattern = r"""<paths_to_keep>(\n)?(?P<paths_to_keep>.*)</paths_to_keep>"""
        paths_to_keep_match = re.search(
            paths_to_keep_pattern, string, re.DOTALL
        )
        for path in paths_to_keep_match.groupdict()[
            "paths_to_keep"
        ].split("\n"):
            path = path.strip()
            path = path.replace("* ", "")
            path = path.replace("...", "")
            if len(path) > 1:
                logger.info(f"paths_to_keep: {path}")
                paths_to_keep.append(path)
        directories_to_expand_pattern = r"""<directories_to_expand>(\n)?(?P<directories_to_expand>.*)</directories_to_expand>"""
        directories_to_expand_match = re.search(
            directories_to_expand_pattern, string, re.DOTALL
        )
        for path in directories_to_expand_match.groupdict()[
            "directories_to_expand"
        ].split("\n"):
            path = path.strip()
            path = path.replace("* ", "")
            path = path.replace("...", "")
            if len(path) > 1:
                logger.info(f"directories_to_expand: {path}")
                directories_to_expand.append(path)
        return cls(
            paths_to_keep=paths_to_keep,
            directories_to_expand=directories_to_expand,
        )

class ContextPruning(ChatGPT):
    def prune_context(self, human_message: HumanMessagePrompt, **kwargs) -> tuple[list[str], list[str]]:
        try:
            content = system_message_prompt
            repo = kwargs.get("repo")
            if repo:
                repo_description = get_description(repo)
                if repo_description:
                    content += f"{repo_description_prefix_prompt}\n{repo_description}"
            self.messages = [Message(role="system", content=content, key="system")]
            added_messages = (
                human_message.construct_prompt(snippet_tag="snippets_in_repo", 
                                               directory_tag="paths_in_repo")
            )  # [ { role, content }, ... ]
            for msg in added_messages:
                self.messages.append(Message(**msg))
            self.model = (
                "gpt-4-32k"
                if (self.chat_logger and self.chat_logger.is_paying_user())
                else "gpt-3.5-turbo-16k-0613"
            )
            response = self.chat(pruning_prompt)
            context_to_prune = ContextToPrune.from_string(response)
            return context_to_prune.paths_to_keep, context_to_prune.directories_to_expand
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return [], []
