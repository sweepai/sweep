"""
This file contains the on_merge handler which is called when a pull request is merged to master.
on_merge is called by sweepai/api.py
"""

from loguru import logger

# change threshold for number of lines changed
CHANGE_BOUNDS = (10, 1500)

# dictionary to map from github repo to the last time a rule was activated
merge_rule_debounce = {}

# debounce time in seconds
DEBOUNCE_TIME = 120

diff_section_prompt = """
<file_diff file="{diff_file_path}">
{diffs}
</file_diff>"""


def comparison_to_diff(comparison, blocked_dirs):
    pr_diffs = []
    for file in comparison.files:
        diff = file.patch
        if (
            file.status == "added"
            or file.status == "modified"
            or file.status == "removed"
        ):
            if any(file.filename.startswith(dir) for dir in blocked_dirs):
                continue
            pr_diffs.append((file.filename, diff))
        else:
            logger.info(
                f"File status {file.status} not recognized"
            )  # TODO(sweep): We don't handle renamed files
    formatted_diffs = []
    for file_name, file_patch in pr_diffs:
        format_diff = diff_section_prompt.format(
            diff_file_path=file_name, diffs=file_patch
        )
        formatted_diffs.append(format_diff)
    return "\n".join(formatted_diffs)
