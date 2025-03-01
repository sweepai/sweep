from sweepai.handlers.on_ticket import on_ticket

def handle_linear_ticket(event):
    """Handle an incoming Linear webhook event."""
    
    # Extract relevant information from the event payload
    ticket_id = event["data"]["id"]
    ticket_title = event["data"]["title"]
    ticket_description = event["data"]["description"]
    ticket_labels = event["data"]["labels"]
    
    # Check if the ticket has the Sweep label
    if any(label["name"].lower() == LINEAR_LABEL_NAME.lower() for label in ticket_labels):
        # Invoke the Sweep workflow
        on_ticket(
            title=ticket_title,
            summary=ticket_description,
            issue_number=ticket_id,
            issue_url=f"https://linear.app/issue/{ticket_id}",
            username=event["data"]["creator"]["name"],
            repo_full_name="",  # TODO: Map Linear project to GitHub repo
            repo_description="",
            installation_id=0,  # TODO: Get GitHub app installation ID
        )