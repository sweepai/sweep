subissues_plan = """
Thoughts:
* The task involves setting up linters for different languages in GitHub Actions, which can be considered as separate subtasks.
* Each subtask requires configuring a specific linter for a particular language.
* Splitting the ticket into multiple smaller tickets will allow for better organization and easier tracking of progress.

split_issue = true

Required Actions:
* Action 1: Split the ticket into separate subtasks for each language (Python, JavaScript, TypeScript).

Ticket 1:
    Title: Set up Black and Pylint for Python in GitHub Actions
    Desc: Configure GitHub Actions to run Black and Pylint checks for Python code.

Ticket 2:
    Title: Set up ESLint for JavaScript in GitHub Actions
    Desc: Configure GitHub Actions to run ESLint checks for JavaScript code.

Ticket 3:
    Title: Set up TSC for TypeScript in GitHub Actions
    Desc: Configure GitHub Actions to run TSC checks for TypeScript code.

Note: Additional tickets can be created if there are more languages or linters to set up."""
import re
# Split by Ticket \d
tickets = re.split(r'Ticket \d:\n', subissues_plan)[1:]
# Get Title: and Desc: in each ticket
tickets = [re.split(r'Title:|Desc:', ticket)[1:] for ticket in tickets]
# Strip
tickets = [[t.strip().split('\n')[0] for t in ticket] for ticket in tickets]


print(tickets)