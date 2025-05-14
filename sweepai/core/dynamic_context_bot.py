import subprocess

from loguru import logger
from sweepai.config.client import SweepConfig
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Snippet
from sweepai.core.snippet_utils import convert_lines_to_and_merge_ranges
from sweepai.core.vector_db import cosine_similarity, embed_text_array
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.ripgrep_utils import cleaned_rg_output, parse_ripgrep_line


# implements a variety of ways to get more context from the code base
class DynamicContextBot(ChatGPT):
    def use_ripgrep(
        self,
        queries: list[str],
        target: str,
        cloned_repo: ClonedRepo,
        exact_match: bool = False,
        case_sensitive: bool = False,
        snippet_context: int = 10,
        k: int = 5,
    ) -> list[Snippet]:
        """
        Use ripgrep on the cloned repo to get all occurances of the queries, ignores files based on sweep_config
        Compares results against the target text to get the best snippets
        Input: list of strings
        Output: list of snippets
        """
        sweep_config = SweepConfig()
        snippets: list[Snippet] = []
        sorted_snippets: list[Snippet] = []
        directory = cloned_repo.repo_dir
        rg_command_base = ["rg", "-n", "--heading"]
        results = []
        for query in queries:
            rg_command = rg_command_base + [f'"{query}"', directory]
            if exact_match:
                rg_command += ["-w"]
            if not case_sensitive:
                rg_command += ["-i"]
            try:
                result = subprocess.run(
                    " ".join(rg_command), text=True, shell=True, capture_output=True
                )
                results = result.stdout
                files_to_results: dict[str, str] = cleaned_rg_output(directory, sweep_config, results)
                # list of line numbers for each file used to get snippets for that file
                files_to_line_numbers: dict[str, list[int]] = {}
                # break each line into line number and line content
                for file_path, content in files_to_results.items():
                    lines = content.split("\n")
                    for line in lines:
                        line_number, _ = parse_ripgrep_line(line)
                        if line_number == -1:
                            logger.warning(f"Error parsing ripgrep line: {line}")
                            continue
                        if file_path not in files_to_line_numbers:
                            files_to_line_numbers[file_path] = []
                        files_to_line_numbers[file_path].append(line_number)
                # get list of ranges for each file to begin creating the snippets
                files_to_ranges: dict[str, list[tuple[int, int]]] = {}
                for file_path, line_numbers in files_to_line_numbers.items():
                    try:
                        file_upper_bound = len(cloned_repo.get_file_contents(file_path).split("\n"))
                        ranges = convert_lines_to_and_merge_ranges(
                            line_numbers, 
                            range_size=20, 
                            lower_bound=0, 
                            upper_bound=file_upper_bound - 1, 
                            offset = -1 # rip grep start counting at 1
                        )
                        files_to_ranges[file_path] = ranges
                    except Exception as e:
                        logger.warning(f"Error converting lines to ranges: {e}")
                        files_to_ranges[file_path] = []
                        continue
                # get the snippets for each file
                for file_path, ranges in files_to_ranges.items():
                    try:
                        file_contents = cloned_repo.get_file_contents(file_path)
                        for start, end in ranges:
                            snippet = Snippet(
                                content=file_contents,
                                file_path=file_path,
                                start=start,
                                end=end,
                            )
                            snippets.append(snippet)
                    except Exception as e:
                        logger.warning(f"Error getting snippets: {e}")
                        continue
                # now we have all the snippets, we can filter them based on the target
                snippet_contents = [snippet.get_snippet(add_lines=False) for snippet in snippets]
                # embed and them compare with the target
                embedded_snippet_contents = embed_text_array(snippet_contents)[0]
                embedded_query = embed_text_array([target])[0]
                similarity_scores = cosine_similarity(embedded_query, embedded_snippet_contents).tolist()[0]
                # update scores for each snippet
                for i, snippet in enumerate(snippets):
                    snippet.score = similarity_scores[i]
                sorted_snippets = sorted(snippets, key=lambda x: x.score, reverse=True)
            except Exception as e:
                logger.warning(f"Error running ripgrep: {e}")
                continue
        return sorted_snippets[:k]
    
if __name__ == "__main__":
    pass
    # context_bot = DynamicContextBot()
    # context_bot.use_ripgrep(["test"], "target", cloned_repo)
