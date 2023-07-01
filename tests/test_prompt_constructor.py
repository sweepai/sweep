from loguru import logger
import difflib
from sweepai.utils.prompt_constructor import HumanMessagePrompt

expected_original_prompt = '''
Repo: sweepai/sweep-test: test_repo_description
Issue: test_issue
Username: test_user
Title: test_title
Description: test_summary

Relevant Directories:
<relevant_directories>
test_file_path_a
test_file_path_b
</relevant_directories>

Relevant Files:
<relevant_files>
```
test_file_path_a
"""
test_file_contents_a
"""
test_file_path_b
"""
test_file_contents_b
"""
```
</relevant_files>
'''

expected_deletion_prompt = '''
Repo: sweepai/sweep-test: test_repo_description
Issue: test_issue
Username: test_user
Title: test_title
Description: test_summary

Relevant Directories:
<relevant_directories>
test_file_path_b
</relevant_directories>

Relevant Files:
<relevant_files>
```
test_file_path_b
"""
test_file_contents_b
"""
```
</relevant_files>
'''

if __name__ == "__main__":
    repo_name = "sweepai/sweep-test"
    issue_url = "test_issue"
    username = "test_user"
    repo_description = "test_repo_description"
    title = "test_title"
    summary = "test_summary"
    file_path_to_contents = {
        "test_file_path_a": "test_file_contents_a",
        "test_file_path_b": "test_file_contents_b",
    }
    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=summary,
        file_path_to_contents=file_path_to_contents,
    )
    constructed_prompt = human_message.construct_prompt()
    expected_lines = expected_original_prompt.splitlines()
    constructed_lines = constructed_prompt.splitlines()

    # Generate the diff output
    if constructed_prompt == expected_original_prompt:
        logger.info("Test passed!")
    else:
        diff = difflib.unified_diff(expected_lines, constructed_lines)
        logger.info("\n".join(diff))
        logger.info("Test failed!")
        logger.info(f"Constructed prompt: {constructed_prompt}")
        logger.info(f"Expected prompt: {expected_original_prompt}")

    # Test delete_file
    human_message.delete_file("test_file_path_a")
    constructed_prompt = human_message.construct_prompt()
    expected_deletion_lines = expected_deletion_prompt.splitlines()
    constructed_lines = constructed_prompt.splitlines()
    if constructed_prompt == expected_deletion_prompt:
        logger.info("Test passed!")
    else:
        diff = difflib.unified_diff(expected_deletion_lines, constructed_lines)
        logger.info("\n".join(diff))
        logger.info("Test failed!")
        logger.info(f"Constructed prompt: {constructed_prompt}")
        logger.info(f"Expected prompt: {expected_deletion_prompt}")
