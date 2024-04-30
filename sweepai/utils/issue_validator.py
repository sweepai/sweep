import re
from sweepai.core.chat import ChatGPT


issue_validator_instructions_prompt = """# Instructions

A good issue for Sweep is specific, actionable and there is sufficient information to resolve it. B bad issue is one that is vague or unclear. Issues involving the following should also not pass, as they are outside the scope of Sweep:
- Large-scale changes like migrations and large version upgrades.
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
</issue>""" + issue_validator_instructions_prompt

def validate_issue(issue: str) -> str:
    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=issue_validator_system_prompt,
    )

    response = chat_gpt.chat(
        issue_validator_user_prompt.format(
            issue=issue
        ),
        temperature=0.0,
    )
    
    if "<pass>False</pass>" in response:
        pattern = "<response_to_user>(.*)</response_to_user>"
        return re.search(pattern, response, re.DOTALL).group(1).strip()
    return ""

if __name__ == "__main__":
    print(validate_issue("The app is slow."))
