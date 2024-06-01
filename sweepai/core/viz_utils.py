from datetime import datetime
from inspect import stack
import os
import re

from loguru import logger
from pytz import timezone
from sweepai.core.entities import Message

pst_timezone = timezone("US/Pacific")

def print_bar_chart(data: dict[str, list]):
    total_length = sum(len(v) for v in data.values())
    max_bar_length = 50
    
    # Sort the data based on the values in descending order
    sorted_data = sorted(data.items(), key=lambda x: len(x[1]), reverse=True)
    
    # Find the length of the longest category name
    max_category_length = max(len(key) for key in data.keys())
    
    for key, value in sorted_data:
        value = len(value)
        ratio = value / total_length
        bar_length = int(ratio * max_bar_length)
        bar = '█' * bar_length
        print(f"{key.ljust(max_category_length)} | {bar} {value}")

def wrap_xml_tags_with_details(text: str) -> str:
    def replace_tag_pair(match):
        tag = match.group(1)
        content = match.group(2)
        return f"<details><summary>&lt;{tag}&gt;</summary>\n\n```xml\n{content}\n```\n\n</details>"
    return re.sub(r'<([^>]+)>(.*?)</\1>', replace_tag_pair, text, flags=re.DOTALL)

def save_messages_for_visualization(messages: list[Message], use_openai: bool):
    current_datetime = datetime.now(pst_timezone).strftime("%Y_%h_%d/%I:%M%p")
    subfolder = f"sweepai_messages/{current_datetime}"
    llm_type = "openai" if use_openai else "anthropic"
    
    os.makedirs(subfolder, exist_ok=True)

    function_names = [frame.function for frame in stack()]
    caller_function_name = "unknown"
    if len(function_names) < 2:
        caller_function_name = "unknown"
    elif function_names[2] != "continuous_llm_calls":
        caller_function_name = function_names[2]
    elif len(function_names) > 3:
        caller_function_name = function_names[3]

    raw_file = os.path.join(subfolder, f'{caller_function_name}.xml')
    md_file = os.path.join(subfolder, f'{caller_function_name}.md')
    # if the md/raw files exist, append _1, _2, etc. to the filename
    for i in range(1, 1000):
        if not os.path.exists(raw_file) and not os.path.exists(md_file):
            break # we can safely use the current filename
        else:
            raw_file = os.path.join(subfolder, f'{caller_function_name}_{i}.xml')
            md_file = os.path.join(subfolder, f'{caller_function_name}_{i}.md')

    with open(raw_file, 'w') as f_raw, open(md_file, 'w') as f_md:
        total_length = 0
        for message in messages:
            content_raw = message.content
            total_length += len(content_raw)
            content_md = wrap_xml_tags_with_details(content_raw)
            token_estimate_factor = 4 if use_openai else 3.5
            message_tokens = int(len(content_raw) // token_estimate_factor)
            message_header = f"{llm_type} {message.role} - {message_tokens} tokens - {int(total_length // token_estimate_factor)} total tokens"
            f_raw.write(f"{message_header}\n{content_raw}\n\n")
            f_md.write(f"## {message_header}\n\n{content_md}\n\n")
    cwd = os.getcwd()
    logger.info(f"Messages saved to {os.path.join(cwd, raw_file)} and {os.path.join(cwd, md_file)}")