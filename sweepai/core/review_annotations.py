import multiprocessing
import re

from loguru import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.logn.cache import file_cache

CLAUDE_MODEL = "claude-3-sonnet-20240229"
NUM_WORKERS = 4 # depends on sonnet rate limit

system_prompt = """You have been provided a diff_to_annotate (a code change), and the source code (the code after this diff was applied).
Analyze the provided source_code and diff_to_annotate. This will later be used to identify any issues.

# Instructions
- Clearly explain how the functionality of the code has changed.
- You must NEVER speculate on why a code change was made.
- Your response must not contain large code chunks.

Respond in the following format:
<diff_analysis>
Analyze the diff, comparing the previous and current state of the code. Focus solely on explaining what has changed functionally, without speculating on the reasons or motivations behind the changes. (1 paragraph)
</diff_analysis>

<diff_annotation>
- Provide an information-dense, objective explanation of each individual code change in diff_to_annotate, without making subjective inferences about why the changes were made.
- Focus on clearly describing what was changed and how it impacts the code's functionality. Do not guess the developer's intentions.
- This explanation may span multiple lines as needed to thoroughly explain the changes.
</diff_annotation>"""

user_prompt = """<source_code>
{source_code}
</source_code>

<diff_to_annotate>
{diff_to_annotate}
</diff_to_annotate>

# Instructions
- Clearly explain how the functionality of the code has changed.
- You must NEVER speculate on why a code change was made.
- Your response must not contain large code chunks.

Respond in the following format:
<diff_analysis>
Analyze the diff, comparing the previous and current state of the code. Focus solely on explaining what has changed functionally, without speculating on the reasons or motivations behind the changes. (1 paragraph)
</diff_analysis>

<diff_annotation>
- Provide an information-dense, objective explanation of each individual code change in diff_to_annotate, without making subjective inferences about why the changes were made.
- Focus on clearly describing what was changed and how it impacts the code's functionality. Do not guess the developer's intentions.
- This explanation may span multiple lines as needed to thoroughly explain the changes.
</diff_annotation>"""

class AnnotateDiffBot(ChatGPT):
    def annotate_diff(
        self,
        source_code: str,
        diff_to_annotate: str,
    ):
        annotate_code_pattern = r"<diff_annotation>(.*?)</diff_annotation>"
        self.messages = [
            Message(
                content=system_prompt,
                role="system",
            ),
        ]
        try:
            diff_annotation_response = self.chat_anthropic(
                content=user_prompt.format(
                    source_code=source_code.strip("\n"),
                    diff_to_annotate=diff_to_annotate.strip("\n"),
                ),
                temperature=0.2,
                model=CLAUDE_MODEL,
                verbose=False,
                use_openai=True
            )
        except Exception as e:
            logger.warning(f"AnnotateDiffBot failed with error: {e}")
            return ""
        diff_annotation_matches = re.search(annotate_code_pattern, diff_annotation_response, re.DOTALL)
        if not diff_annotation_matches or not diff_annotation_matches.group(1).strip():
            return ""
        diff_annotation = diff_annotation_matches.group(1)
        diff_annotation = diff_annotation.strip()
        return diff_annotation

def process_chunk(idx, diff, source_code, file_name):
    annotation = AnnotateDiffBot().annotate_diff(
        source_code=source_code,
        diff_to_annotate=diff,
    )
    if not annotation:
        annotation = "No annotation was provided for this diff."
    return annotation

@file_cache()
def get_diff_annotations(source_code: str, diffs: list[str], file_name: str):
    pool = multiprocessing.Pool(processes=NUM_WORKERS)
    results = [
        pool.apply_async(process_chunk, args=(idx, diff, source_code, file_name))
        for idx, diff in enumerate(diffs)
    ]
    pool.close()
    pool.join()
    annotations = []
    for result in results:
        annotation = result.get()
        annotations.append(annotation)
    return annotations