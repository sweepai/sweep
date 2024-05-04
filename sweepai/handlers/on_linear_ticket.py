import os
from typing import Any, Dict

from loguru import logger
from sweepai.handlers.on_ticket import on_ticket

LINEAR_LABEL_NAME = os.environ.get("LINEAR_LABEL_NAME", "sweep")

def handle_linear_ticket(event: Dict[str, Any]):
    try:
        ticket_data = event["data"]["issue"]
        ticket_labels = ticket_data.get("labels", {})

        if any(label["name"].lower() == LINEAR_LABEL_NAME.lower() for label in ticket_labels.get("nodes", [])):
            logger.info(f"Sweep label detected on Linear ticket {ticket_data['id']}")
            
            on_ticket(
                title=ticket_data["title"],
                summary=ticket_data["description"],
                issue_number=ticket_data["identifier"], 
                issue_url=ticket_data["url"],
                username=ticket_data["createdBy"]["name"],
                repo_full_name=os.environ.get("LINEAR_GITHUB_REPO"), 
                repo_description="",
                installation_id=int(os.environ.get("LINEAR_GITHUB_INSTALLATION_ID")), 
            )
        else:
            logger.info(f"Sweep label not found on Linear ticket {ticket_data['id']}")

    except Exception as e:
        logger.exception(f"Error processing Linear webhook event: {e}")