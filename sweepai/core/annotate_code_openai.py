import multiprocessing
import re

from loguru import logger
from tqdm import tqdm
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.logn.cache import file_cache
from sweepai.utils.code_validators import chunk_code

CLAUDE_MODEL = "claude-3-haiku-20240307"
NUM_WORKERS = 4 # tune based on haiku rate limit

system_prompt = """Analyze the provided source_code, GitHub issue, and code_to_annotate to generate an explanation with the following format:

<analysis>
Describe what this block of code does as if you were explaining it to an junior engineer.
</analysis>

<code_annotation>
- Information-dense explanation of each block of code in code_to_annotate.
- This explanation may span over multiple lines.
</code_annotation>"""

user_prompt = """<source_code>
{source_code}
</source_code>

<issue>
{issue}
</issue>

<code_to_annotate>
{code_to_annotate}
</code_to_annotate>

Analyze the provided source_code, GitHub issue, and code_to_annotate to generate an explanation with the following format:

<analysis>
Describe what this block of code does as if you were explaining it to an junior engineer.
</analysis>

<code_annotation>
- Information-dense explanation of each block of code in code_to_annotate.
- This explanation may span over multiple lines.
</code_annotation>""" # prompt can be optimized

class AnnotateCodeBot(ChatGPT):
    def annotate_code(
        self,
        source_code: str,
        issue_text: str,
        code_to_annotate: str,
    ):
        annotate_code_pattern = r"<code_annotation>(.*?)</code_annotation>"
        self.messages = [
            Message(
                content=system_prompt,
                role="system",
            ),
        ]
        try:
            code_annotation_response = self.chat_anthropic(
                content=user_prompt.format(
                    source_code=source_code.strip("\n"),
                    issue=issue_text.strip("\n"),
                    code_to_annotate=code_to_annotate.strip("\n"),
                ),
                temperature=0.2,
                model=CLAUDE_MODEL,
                verbose=False
            )
        except Exception as e:
            logger.warning(f"AnnotateCodeBot failed with error: {e}")
            return ""
        code_annotation_matches = re.search(annotate_code_pattern, code_annotation_response, re.DOTALL)
        if not code_annotation_matches or not code_annotation_matches.group(1).strip():
            return ""
        code_annotation = code_annotation_matches.group(1)
        code_annotation = code_annotation.strip()
        return code_annotation

def process_chunk(idx, code_content, source_code, issue_text, file_path):
    annotation = AnnotateCodeBot().annotate_code(
        source_code=source_code,
        issue_text=issue_text,
        code_to_annotate=code_content,
    )
    if not annotation:
        annotation = "No summary was provided for this code block."
    formatted_code_content = f'<original_code file_path="{file_path}" index="{idx}">\n' + code_content + "\n</original_code>\n"
    formatted_annotation = f'<code_summary file_path="{file_path}" index="{idx}">\n' + annotation + "\n</code_summary>\n"
    return idx, formatted_code_content, formatted_annotation

@file_cache(ignore_params=["issue_text"]) # safe to cache
def get_annotated_source_code(source_code: str, issue_text: str, file_path: str):
    annotated_source_code = source_code
    code_chunks = chunk_code(source_code, file_path, MAX_CHARS=60 * 50)
    code_contents = [chunk.get_snippet(False, False) for chunk in code_chunks]

    if NUM_WORKERS > 1:
        pool = multiprocessing.Pool(processes=NUM_WORKERS)
        results = [
            pool.apply_async(process_chunk, args=(idx, code_content, source_code, issue_text, file_path))
            for idx, code_content in enumerate(code_contents)
        ]
        pool.close()
        pool.join()
        code_with_summaries = []
        for result in results:
            chunk_result = result.get()
            if chunk_result is not None:
                idx, formatted_code_content, formatted_annotation = chunk_result
                code_with_summary = f"{formatted_code_content + formatted_annotation}"
                annotated_source_code = annotated_source_code.replace(code_contents[idx], code_with_summary, 1)
                code_with_summaries.append(code_with_summary)
    else:
        code_with_summaries = []
        for idx, code_content in enumerate(tqdm(code_contents)):
            annotation = AnnotateCodeBot().annotate_code(
                source_code=source_code,
                issue_text=issue_text,
                code_to_annotate=code_content,
            )
            if not annotation:
                annotation = "No summary was provided for this code block."
            formatted_code_content = f'<original_code file_path="{file_path}" index="{idx}">\n' + code_content + "\n</original_code>\n"
            formatted_annotation = f'<code_summary file_path="{file_path}" index="{idx}">\n' + annotation + "\n</code_summary>\n"
            code_with_summary = f"{formatted_code_content + formatted_annotation}"
            annotated_source_code = annotated_source_code.replace(code_content, code_with_summary, 1)
            code_with_summaries.append(code_with_summary)
    return annotated_source_code.strip("\n"), code_with_summaries

if __name__ == '__main__':
    source_code = ""
    issue_text = ""
    file_path = ""
    get_annotated_source_code(source_code, issue_text, file_path)