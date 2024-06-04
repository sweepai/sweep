import re
from sweepai.core.chat import ChatGPT


issue_validator_instructions_prompt = """# Instructions

A good issue for Sweep is actionable and it is clear how to resolve it. Here is what Sweep is currently capable of:
- Access to the entire codebase, with a high-quality search engine to find specific code snippets. Sweep is able to pinpoint the exact location of the code that needs to be changed based on vague descriptions.
- Making code changes to fix bugs or add features.
- Reading the GitHub Action logs to run tests and check the results.
- Ability to read images such as screenshots and charts.

Here are some examples of things Sweep does not currently support:
- Large-scale changes like migrations and large version upgrades.
- Copying and pasting large amounts of code, including large files or directories.
- Command line operations, such as updating an npm lockfile.
- Tasks requiring accessing outside information like AWS consoles or retrieving API keys.
- Tasks requiring fixes outside of code changes
- Issues that have an existing fix or duplicate issues

Respond in the following format:

<thinking>
Provide an analysis of why it is a good or bad issue to pass on to Sweep. If it is a bad issue, suggest how the issue could be improved or clarified to make it more suitable for Sweep.
</thinking>

<pass>True or False</pass>

If False, respond to the user:
<response_to_user>
Response to user with justification on why the issue is unclear.
</response_to_user>"""

issue_validator_system_prompt = """You are an AI assistant tasked with determining whether an issue reported by customer support should be passed on to be resolved by Sweep, an AI-powered software engineer.

""" + issue_validator_instructions_prompt

issue_validator_user_prompt = """<issue>
{issue}
</issue>\n\n""" + issue_validator_instructions_prompt

def validate_issue(issue: str) -> str:
    """
    Somehow haiku and GPT-4 can't do this consistently.
    """
    chat_gpt: ChatGPT = ChatGPT.from_system_message_string(
        prompt_string=issue_validator_system_prompt,
    )

    response = chat_gpt.chat_anthropic(
        issue_validator_user_prompt.format(
            issue=issue
        ),
        model="claude-3-opus-20240229",
        temperature=0.0,
    )
    
    if "<pass>False</pass>" in response:
        pattern = "<response_to_user>(.*)</response_to_user>"
        return re.search(pattern, response, re.DOTALL).group(1).strip()
    return ""

if __name__ == "__main__":
    print(validate_issue("The app is slow."))
