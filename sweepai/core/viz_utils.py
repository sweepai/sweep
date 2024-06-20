import html
import os
from datetime import datetime
from inspect import stack
import re
from pytz import timezone

from loguru import logger
from sweepai.core.entities import Message

pst_timezone = timezone("US/Pacific")

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

def escape_xml(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def wrap_content_with_details(content: str, header: str) -> str:
    return f'<details><summary>{header}</summary>\n\n```xml\n{content}\n```\n\n</details>'

def wrap_xml_tags_with_details(text: str) -> str:
    def process_tag(match):
        full_tag = match.group(0)
        is_closing = full_tag.startswith('</')
        
        if is_closing:
            return '</details>'
        else:
            escaped_tag = html.escape(full_tag)
            return f'<details><summary>{escaped_tag}</summary>'

    # First, wrap all XML tags with details/summary structure
    processed_text = re.sub(r'<[^>]+>', process_tag, text)
    
    # Then, escape any remaining < and > characters that aren't part of our details/summary structure
    lines = processed_text.split('\n')
    for i, line in enumerate(lines):
        if not (line.strip().startswith('<details') or line.strip().startswith('</details') or line.strip().startswith('<summary')):
            lines[i] = html.escape(line)
    
    processed_text = '\n'.join(lines)
    
    return processed_text

functions_to_unique_f_locals_string_getter = {
    "on_ticket": lambda x: "issue_" + str(x["issue_number"]),
    "review_pr": lambda x: "pr_" + str(x["pr"].number),
    "on_failing_github_actions": lambda x: "pr_" + str(x["pull_request"].number),
} # just need to add the function name and the lambda to get the unique f_locals

# these are common wrappers that we don't want to use as our caller_function_name
llm_call_wrappers = ["continuous_llm_calls", "call_llm", "_bootstrap_inner"]

def save_messages_for_visualization(messages: list[Message], use_openai: bool, model_name: str):
    current_datetime = datetime.now(pst_timezone)
    current_year_month_day = current_datetime.strftime("%Y_%h_%d")
    current_hour_minute_second = current_datetime.strftime("%I:%M:%S%p")
    subfolder = f"sweepai_messages/{current_year_month_day}"
    llm_type = "openai" if use_openai else "anthropic"
    
    os.makedirs(subfolder, exist_ok=True)

    # goes up the stack to unify shared logs
    frames = stack()
    function_names = [frame.function for frame in frames]
    for i, function_name in enumerate(function_names):
        if function_name in functions_to_unique_f_locals_string_getter:
            unique_f_locals = functions_to_unique_f_locals_string_getter[function_name](frames[i].frame.f_locals)
            subfolder = os.path.join(subfolder, f"{function_name}_{unique_f_locals}")
            os.makedirs(subfolder, exist_ok=True)
            break
        else:
            # terminate on the second to last item
            if i == len(function_names) - 2:
                subfolder = os.path.join(subfolder, f"{current_hour_minute_second}_{function_name}")
                os.makedirs(subfolder, exist_ok=True)
    # finished going up the stack
    caller_function_name = "unknown"
    if len(function_names) < 2:
        caller_function_name = "unknown"
    for i in range(2, len(function_names)):
        if function_names[i] not in llm_call_wrappers:
            caller_function_name = function_names[i]
            break

    # add the current hour and minute to the caller function name
    caller_function_name = f"{current_hour_minute_second}_{caller_function_name}"

    raw_file = os.path.join(subfolder, f'{caller_function_name}.xml')
    html_file = os.path.join(subfolder, f'{caller_function_name}.html')
    # if the html/raw files exist, append _1, _2, etc. to the filename
    for i in range(1, 1000):
        if not os.path.exists(raw_file) and not os.path.exists(html_file):
            break # we can safely use the current filename
        else:
            raw_file = os.path.join(subfolder, f'{caller_function_name}_{i}.xml')
            html_file = os.path.join(subfolder, f'{caller_function_name}_{i}.html')

    with open(raw_file, 'w') as f_raw, open(html_file, 'w') as f_html:
        f_html.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Message Visualization</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            line-height: 1.6; 
            padding: 20px; 
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        h2 { 
            margin-top: 20px; 
            background-color: #0050a0;
            color: #ffffff;
            padding: 10px;
            border-radius: 5px;
        }
        details { 
            margin-bottom: 10px; 
            background-color: #2a2a2a;
            border: 1px solid #444;
            border-radius: 5px;
            padding: 10px;
        }
        summary { 
            cursor: pointer; 
            font-weight: bold;
            background-color: #333333;
            color: #ffffff;
            padding: 5px;
            border-radius: 3px;
            margin-bottom: 10px;
        }
        .nested-details {
            margin-left: 20px;
            border-left: 3px solid #0078d4;
            padding-left: 10px;
        }
    </style>
</head>
<body>
''')
        total_length = 0
        for message in messages:
            try:
                content_raw = message.content
                total_length += len(content_raw)
                content_html = wrap_xml_tags_with_details(content_raw)
                token_estimate_factor = 4 if use_openai else 3.5
                message_tokens = int(len(content_raw) // token_estimate_factor)
                message_header = f"{llm_type} {model_name} {message.role} - {message_tokens} tokens - {int(total_length // token_estimate_factor)} total tokens"
                f_raw.write(f"{message_header}\n{content_raw}\n\n")
                f_html.write(f"<h2>{html.escape(message_header)}</h2>\n<div>{content_html}</div>\n\n")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                f_raw.write(f"Error in message processing: {e}\nRaw content: {content_raw}\n\n")
                f_html.write(f"<h2>Error in message processing</h2>\n<pre>{html.escape(str(e))}\n{html.escape(content_raw)}</pre>\n\n")

        f_html.write('</body></html>')

    cwd = os.getcwd()
    logger.info(f"Messages saved to {os.path.join(cwd, raw_file)} and {os.path.join(cwd, html_file)}")