import re

from loguru import logger
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from sweepai.config.server import SLACK_API_KEY

def get_thread_by_thread_ts(client: WebClient, channel_id: int, thread_ts: int):
    response = client.conversations_replies(
        channel=channel_id,
        ts=thread_ts
    )
    
    if response["ok"]:
        return response["messages"]
    else:
        print(f"Error fetching thread: {response['error']}")
        return None

def add_slack_context(summary) -> str:
    result = ""
    if not SLACK_API_KEY:
        return result
    slack_link_match = re.search(r'(https://[\w-]+\.slack\.com/archives/\w+/p\d+)', summary)
    if not slack_link_match:
        return result
    slack_link = slack_link_match.group(1)
    slack_client = WebClient(token=SLACK_API_KEY)
    try:
        # Extract channel and message_ts from the Slack link
        link_parts = slack_link.split('/')
        slack_channel_id = link_parts[-2]
        slack_message_ts = link_parts[-1][1:]  # Remove the 'p' prefix
        # you need to add a dot six places from the right
        slack_message_ts = f"{slack_message_ts[:-6]}.{slack_message_ts[-6:]}"
        # Fetch the message object
        thread_messages = get_thread_by_thread_ts(client=slack_client, channel_id=slack_channel_id, thread_ts=slack_message_ts)
        if len(thread_messages) > 0:
            result += f"\n\nThe following slack thread was attached to {slack_link}:\n<slack_thread>\n"
        for idx, thread_message in enumerate(thread_messages):
            result += f"Message {idx}: {thread_message['text']}\n" if "text" in thread_message else ""
        result += "</slack_thread>"
    except SlackApiError as e:
        logger.error(f"Error fetching Slack message or thread: {e}")
    return result
    
if __name__ == "__main__":
    url = ""
    result = add_slack_context(url)
    print(result)