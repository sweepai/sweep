from sweepai.core.chat import call_llm
from sweepai.utils.str_utils import extract_xml_tag


instructions = """I'm going to give you a GitHub issue. Please carefully read the issue description and identify any specific entities mentioned that are critical to the issue that I must find all occurrences of. This should be an uncommon term in the relevant files. Give me a brief set of at most 5 entity names that you should grep for in the provided files, prioritizing the ones directly related to the specific entities mentioned in the issue, and those that are uncommon in this codebase. Grepping these entity names should be helpful with finding the right places to make changes.

Respond in this format:

<entities>
Lists of new line separated entities.
</entities>"""

def get_list_of_entities(
    message: str,
):
    response = call_llm(
        system_prompt=instructions,
        user_prompt=message + "\n\n" + instructions,
        use_openai=True,
    )
    entities = extract_xml_tag(response, "entities")
    return [entity.strip() for entity in entities.split("\n")]
