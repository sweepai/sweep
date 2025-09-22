import os
from typing import Any, Dict

from loguru import logger

LINEAR_LABEL_NAME = os.environ.get("LINEAR_LABEL_NAME", "sweep")

def handle_linear_ticket(event: Dict[str, Any]):
    try:
        ticket_data = event["data"]
        ticket_labels = ticket_data.get("labels", [])

        if any(label["name"].lower() == LINEAR_LABEL_NAME.lower() for label in ticket_labels):
            logger.info(f"Sweep label detected on Linear ticket {ticket_data['id']}")
            # TODO: Implement Sweep workflow logic here
            # Reference on_jira_ticket.py for how to process the ticket and kick off Sweep
        else:
            logger.info(f"Sweep label not found on Linear ticket {ticket_data['id']}")

    except Exception as e:
        logger.exception(f"Error processing Linear webhook event: {e}")