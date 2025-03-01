import os
from typing import Any, Dict

from loguru import logger
from sweepai.handlers.on_ticket import on_ticket

LINEAR_LABEL_NAME = os.environ.get("LINEAR_LABEL_NAME", "sweep")

def handle_linear_ticket(event: Dict[str, Any]):
    try:
        ticket_data = event["data"]
        ticket_labels = ticket_data.get("labels", [])

        if any(label["name"].lower() == LINEAR_LABEL_NAME.lower() for label in ticket_labels):
            logger.info(f"Sweep label detected on Linear ticket {ticket_data['id']}")
            
            on_ticket(
                title=ticket_data["title"],
                summary=ticket_data["description"],
                issue_number=ticket_data["number"], 
                issue_url=ticket_data["url"],
                username=ticket_data["creator"]["name"],
                repo_full_name="linear_repo", # TODO: Map Linear team to GitHub repo  
                repo_description="",
                installation_id=0, # TODO: Get GitHub app installation ID
            )
        else:
            logger.info(f"Sweep label not found on Linear ticket {ticket_data['id']}")

    except Exception as e:
        logger.exception(f"Error processing Linear webhook event: {e}")