from typing import Dict

from sweepai.utils.event_logger import logger

def handle_linear_ticket(event: Dict):
    """Handle a Linear ticket event."""
    logger.info(f"Received Linear ticket event: {event}")
    
    # Extract relevant information from the event payload
    ticket_id = event["data"]["id"]
    ticket_title = event["data"]["title"]
    ticket_description = event["data"]["description"]
    
    # Check if the ticket has the "Sweep" label
    has_sweep_label = any(label["name"] == "Sweep" for label in event["data"]["labels"]["nodes"])
    
    if has_sweep_label:
        # Invoke the Sweep workflow for the Linear ticket
        logger.info(f"Linear ticket {ticket_id} has the Sweep label, invoking Sweep workflow")
        # TODO: Implement Sweep workflow for Linear tickets
    else:
        logger.info(f"Linear ticket {ticket_id} does not have the Sweep label, ignoring")