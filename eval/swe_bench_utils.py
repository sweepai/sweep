from __future__ import annotations
from time import time

import os

from rich.console import Console
from rich import print

from sweepai.agents.modify_bot import ModifyBot
from sweepai.core.context_pruning import RepoContextManager, get_relevant_context
from sweepai.core.entities import (
    FileChangeRequest,
    Message,
    PullRequest,
)
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger

from sweepai.utils.github_utils import (
    MockClonedRepo,
)

from sweepai.utils.ticket_utils import prep_snippets
import re

import backoff
from sweepai.core.entities import (
    RegexMatchError,
    Snippet,
)
from sweepai.utils.openai_proxy import OpenAIProxy
from sweepai.core.prompts import files_to_change_prompt, files_to_change_system_prompt

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL
from benchmark.repo_imports.build_tree_for_python import build_import_graph


def cprint(*args, **kwargs):
    try:
        Console().print(*args, **kwargs)
    except Exception:
        print(*args, **kwargs)
debug = True
verbose = False

def checkout_to_pr_ref(
    pr_base_sha: str, cloned_repo: MockClonedRepo
):
    try:
        # checkout to pr ref
        cloned_repo.git_repo.git.reset(pr_base_sha, hard=True)
    except Exception as e:
        print(f"Exception occured while attempting to checkout to pr ref: {e}")
        raise e

def evaluate_search(
    rcm: RepoContextManager,
    resolution_files: list[str],
    problem_statement: str,
    k: int,
    name: str,
):
    selected_snippets, all_snippets = rcm.current_top_snippets, rcm.snippets
    content_to_lexical_score = rcm.snippet_scores
    sorted_snippets = sorted(
        all_snippets,
        key=lambda snippet: content_to_lexical_score[snippet.denotation],
        reverse=True,
    )
    sorted_snippet_paths = [snippet.file_path for snippet in sorted_snippets]
    top_k_paths = [
        snippet.file_path for snippet in selected_snippets
    ]  # NOTE: a false positive will hurt the score badly - need to fix
    mrr = 0
    accuracy = 1
    positions = []
    for resolution_file in resolution_files:
        if resolution_file not in sorted_snippet_paths:
            cprint(
                f"Resolution file {resolution_file} is NOT reachable!", style="bold red"
            )
        if resolution_file in top_k_paths:
            mrr += 1 / (top_k_paths.index(resolution_file) + 1)
        if resolution_file in sorted_snippet_paths:
            positions.append(sorted_snippet_paths.index(resolution_file))
        else:
            positions.append(9999)
        # if a resolution file is not in the top k, accuracy is 0
        if resolution_file not in top_k_paths:
            accuracy = 0
    max_mrr_score = sum([1 / (i + 1) for i in range(len(resolution_files))])
    mrr /= max_mrr_score

    cprint(
        f"MRR at {k}: {mrr}\ntest {name}"
    )
    if debug:
        cprint(f"Query: {problem_statement}")
    with open(f"eval/test_outputs.txt", "a") as f:
        test_config_string = f"MRR at {k}: {mrr}\ntest {name}"
        f.write(f"{test_config_string}\n")
        f.close()
    # print the top k snippets and highlight the ones that are in the resolution files
    if debug:
        for snippet in selected_snippets:
            snippet_score = round(content_to_lexical_score[snippet.denotation], 4)
            if snippet.file_path in resolution_files:
                cprint(
                    f"snippet_score {snippet_score}: [green]{snippet.denotation}[/green]"
                )
            else:
                cprint(f"snippet_score {snippet_score}: {snippet.denotation}")
            if verbose:
                cprint(f"{snippet.denotation}: {snippet.content}")
            with open(
                f"eval/output_scores.txt", "a"
            ) as f:
                snippet_string = f"snippet_score {snippet_score}: {snippet.denotation}\n {snippet.denotation}: {snippet.content}"
                f.write(f"{snippet_string}\n")
                f.close()
        # if a resolution file is not in the top k, print it in red
        for resolution_file in resolution_files:
            snippet = [
                snippet
                for snippet in sorted_snippets
                if snippet.file_path == resolution_file
            ][0]
            snippet_score = round(content_to_lexical_score[snippet.denotation], 4)
            if resolution_file not in top_k_paths:
                cprint(
                    f"snippet_score {snippet_score}: [red]{resolution_file} MISSED at rank {sorted_snippet_paths.index(resolution_file) + 1}/{len(sorted_snippet_paths)}[/red]"
                )
    return mrr, accuracy, positions


def evaluate_context(
    rcm: RepoContextManager,
    resolution_files: list[str],
    problem_statement: str,
    k: int,
    name: str,
):
    selected_snippets, all_snippets = rcm.current_top_snippets, rcm.snippets
    content_to_lexical_score = rcm.snippet_scores
    sorted_snippet_paths = [snippet.file_path for snippet in all_snippets]
    top_k_paths = [
        snippet.file_path for snippet in selected_snippets
    ]  # NOTE: a false positive will hurt the score badly - need to fix
    mrr = 0
    accuracy = 1
    positions = []
    for resolution_file in resolution_files:
        if resolution_file not in sorted_snippet_paths:
            cprint(
                f"Resolution file {resolution_file} is NOT reachable!", style="bold red"
            )
        if resolution_file in top_k_paths:
            mrr += 1 / (top_k_paths.index(resolution_file) + 1)
        if resolution_file in sorted_snippet_paths:
            positions.append(sorted_snippet_paths.index(resolution_file))
        else:
            positions.append(9999)
        # if a resolution file is not in the top k, accuracy is 0
        if resolution_file not in top_k_paths:
            accuracy = 0
    max_mrr_score = sum([1 / (i + 1) for i in range(len(resolution_files))])
    mrr /= max_mrr_score

    cprint(
        f"MRR at {k}: {mrr}\ntest {name}"
    )
    if debug:
        cprint(f"Query: {problem_statement}")
    with open(f"eval/test_outputs.txt", "a") as f:
        test_config_string = f"MRR at {k}: {mrr}\ntest {name}"
        f.write(f"{test_config_string}\n")
        f.close()
    # print the top k snippets and highlight the ones that are in the resolution files
    if debug:
        # if a resolution file is not in the top k, print it in red
        for resolution_file in resolution_files:
            snippet = [
                snippet
                for snippet in all_snippets
                if snippet.file_path == resolution_file
            ][0]
            snippet_score = round(content_to_lexical_score[snippet.denotation], 4)
            if resolution_file not in top_k_paths:
                cprint(
                    f"snippet_score {snippet_score}: [red]{resolution_file} MISSED at rank {sorted_snippet_paths.index(resolution_file) + 1}/{len(sorted_snippet_paths)}[/red]"
                )
    return mrr, accuracy, positions

# @file_cache()
def run_search_test(
    cloned_repo: MockClonedRepo,
    problem_statement: str,
    commit_hash: str,
    k: int = 15,
    resolution_files: list[str] = [],
    name: str = ""
) -> tuple[int, int, RepoContextManager, PullRequest]:
    start = time()
    checkout_to_pr_ref(commit_hash, cloned_repo)
    rcm = prep_snippets(cloned_repo, problem_statement, ticket_progress=None, k=k)
    end = time()
    cprint(f"Search elapsed time: {end - start} seconds")

    search_mrr, search_accuracy, search_positions = evaluate_search(
        rcm,
        resolution_files,
        problem_statement,
        k,
        name,
    )
    import_graph = build_import_graph(f"{cloned_repo.repo_dir}/")
    rcm = get_relevant_context(problem_statement, rcm, chat_logger=ChatLogger({
        "username": "__swe_bench_benchmark__",
        "title": f"Benchmarking context {name}",
    }), import_graph=import_graph)
    # # sort all snippets by score inside of content_to_lexical_score

    end = time()
    cprint(f"Total elapsed time: {end - start} seconds")

    mrr, accuracy, positions = evaluate_context(
        rcm,
        resolution_files,
        problem_statement,
        k,
        name,
    )

    return rcm, search_mrr, search_accuracy, search_positions, mrr, accuracy, positions

@file_cache()
def chat(
    messages: list[Message],
    message_key: str = "files_to_change",
    seed: int = 0,
):
    model = DEFAULT_GPT4_32K_MODEL
    temperature = 0
    messages.append(
        Message(
            role="assistant",
            content=call_openai(
                model=model,
                temperature=temperature,
                messages=messages,
                # requested_max_tokens=max_tokens,
                seed=seed,
            ).choices[0].message.content,
            key=message_key,
        )
    )
    return messages[-1].content


@file_cache()
def call_openai(model: str, temperature: int, messages: list[Message], seed: int = 0):

    messages_dicts = []
    for message in messages:
        messages_dicts.append({"role": message.role, "content": message.content})

    global retry_counter
    retry_counter = 0

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=16,
        jitter=backoff.random_jitter,
    )
    def fetch():
        global retry_counter
        retry_counter += 1
        try:
            output = None
            output = OpenAIProxy().call_openai(
                model=model,
                messages=messages_dicts,
                max_tokens=4096,
                temperature=temperature,
                seed=seed,
            )
            return output
        except SystemExit:
            raise SystemExit
        except Exception as e:
            print(f"Exception occured during fetch{e}")
            raise e

    result = fetch()
    return result

def get_files_to_change(
    relevant_snippets: list[Snippet], problem_statement, repo_name, seed: int = 0
) -> tuple[list[FileChangeRequest], str]:
    file_change_requests: list[FileChangeRequest] = []
    messages: list[Message] = []
    messages.append(
        Message(role="system", content=files_to_change_system_prompt, key="system")
    )
    messages.append(
        Message(role="user", content=files_to_change_prompt, key="assistant")
    )
    messages.append(
        Message(
            role="user",
            content=f"# Repo & Issue Metadata\nRepo: {repo_name}\nIssue: {problem_statement}",
            key="assistant",
        )
    )
    relevant_snippet_template = '<relevant_snippets_in_repo>\n<snippet source="{snippet_denotation}">{content}</snippet>\n</relevant_snippets_in_repo>'
    # attach all relevant snippets
    for snippet in relevant_snippets:
        messages.append(
            Message(
                role="user",
                content=relevant_snippet_template.replace(
                    "{snippet_denotation}", snippet.denotation
                ).replace("{content}", snippet.get_snippet(add_lines=False)),
                key="relevant_snippets",
            )
        )
    try:
        print("messages")
        for message in messages:
            print(message.content + "\n\n")
        files_to_change_response = chat(messages, seed=seed)
        print("files_to_change_response", files_to_change_response)
        file_change_requests = []
        for re_match in re.finditer(
            FileChangeRequest._regex, files_to_change_response, re.DOTALL
        ):
            file_change_request = FileChangeRequest.from_string(re_match.group(0))
            file_change_requests.append(file_change_request)
        return file_change_requests, files_to_change_response
    except RegexMatchError as e:
        print("RegexMatchError", e)

    return [], ""

@file_cache()
def run_modify_bot(
    code: str,
    instructions: str,
    file_path: str,
    start_line: int,
    end_line: int,
    additional_messages: list[Message],
    relevant_filepaths: list[str] = [],
    cloned_repo: MockClonedRepo = None,
):
    modify_bot = ModifyBot(
        additional_messages=additional_messages,
        chat_logger=ChatLogger(
            {
                "username": "__swe_bench_benchmark__",
                "title": f"Benchmarking '{file_path}'",
            }
        ),
        parent_bot=None,
        old_file_contents=code,
    )
    return modify_bot.try_update_file(
        file_path=os.path.join(file_path),
        file_contents=code,
        file_change_request=FileChangeRequest(
            filename=os.path.join(file_path),
            change_type="modify",
            instructions=instructions,
            start_line=start_line,
            end_line=end_line,
        ),
        cloned_repo=cloned_repo,
        relevant_filepaths=relevant_filepaths,
    )