import json
from sweepai.handlers.on_jira_ticket import handle_jira_ticket

def test_handle_jira_ticket():
    # load jira event from tests/data/jira_event.json
    with open("tests/data/jira_event.json") as f:
        event = json.load(f)
    # call handle_jira_ticket with the event
    result = handle_jira_ticket(event)

if __name__ == "__main__":
    test_handle_jira_ticket()