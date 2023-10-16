from __future__ import annotations

import re

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

from sweepai.logn import logger

system_prompt = """
Your name is Sweep bot. You are a brilliant and meticulous engineer in charge of creating a contribution guide that contributors must follow when submitting PRs to this repository.  Create the initial set of rules that contributors should follow based off of the given commit history. The commit history is formatted in the following way:
<relevant-commit-history>
<commit> 
first commit in universal diff formant
</commit>
<commit> 
second commit in universal diff formant
</commit>
</relevant-commit-history>
Output rules that are consistent with the commit history and that focus on the code styling. Output the 5 best rules that you can come up with. If a rule does not adhere to good coding standards do not include output it. Rules should not contain any pronouns. Rules should not be related to git.

Below is an example of the format you should output the rules in, do not state the rule number:
<rule-set>
<rule> rule1 </rule>
<rule> rule2 </rule>
<rule> rule3 </rule>
<rule> rule4 </rule>
<rule> rule5 </rule>
</rule-set>

Below is a set of example rules that are considered high quality: 
<rule>There should not be large chunks of code that are just commented out. Docstrings and explanations in code are okay though.<rule>
<rule>Make sure all error logs use traceback during exceptions.<rule>
<rule>There should be no instances of `import pdb; pdb.set_trace()` in production code.<rule>
<rule>There should be no debug log or print statements in production code.<rule>
"""

sweep_yaml_user_prompt = """
<relevant-commit-history>
{commit_history}
</relevant-commit-history>
"""


class SweepYamlBot(ChatGPT):
    def get_sweep_yaml_rules(
        self, commit_history: str
    ):
        if len(commit_history) == 0:
            return ""
        self.messages = [
            Message(
                role="system",
                content=system_prompt,
                key="system",
            )
        ]
        user_prompt = sweep_yaml_user_prompt.format(
            commit_history=commit_history,
        )
        self.model = "gpt-4-32k-0613"
        response = self.chat(user_prompt)
        logger.info(f"CHAT GPT response {response} {type(response)}")

        # format response from gpt
        additional_rules = self.format_sweep_yaml_rules(response)
        logger.info(f"additional rules to add {additional_rules}")
        return additional_rules

    """ 
    Ensure the following format:
     - "rule 1"
     - "rule 2"
     - "rule 3"
     - "rule 4"
     - "rule 5"
    We will return this a string
    """ 
    def format_sweep_yaml_rules(self, response: str):
        pattern = r'<rule>\s*(.*?)\s*</rule>'
        rules = re.findall(pattern, response, re.DOTALL)
        logger.info(f"Successfully added {len(rules)} additional rules.")
        if rules:
            return '- "'  + '"\n- "'.join(rules) + '"'
        return ""

