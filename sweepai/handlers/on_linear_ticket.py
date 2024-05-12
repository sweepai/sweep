from typing import Dict

from sweepai.utils.event_logger import logger

def handle_linear_ticket(event: Dict):
    """Handle a Linear ticket event."""
    logger.info(f"Received Linear ticket event: {event}")
    
    # Extract relevant information from the event payload
    ticket_id = event["data"]["id"]
    
    
    
    # Check if the ticket has the "Sweep" label
    has_sweep_label = any(label["name"] == "Sweep" for label in event["data"]["labels"]["nodes"])
    
    if has_sweep_label:
        # Invoke the Sweep workflow for the Linear ticket
        logger.info(f"Linear ticket {ticket_id} has the Sweep label, invoking Sweep workflow")
        from sweepai.handlers.on_ticket import on_ticket

        ticket_description = event["data"]["description"]
        on_ticket(
            title=f"Linear Ticket {ticket_id}: {event['data']['title']}",
            summary=ticket_description,
            issue_number=ticket_id,
            issue_url=event["url"],
            username=event["data"]["creator"]["name"],
            repo_full_name="linear_repo", # Get repo name from Linear ticket
            repo_description="",
            installation_id=0, # Map Linear user to GitHub installation ID
        )
    else:
        logger.info(f"Linear ticket {ticket_id} does not have the Sweep label, ignoring")