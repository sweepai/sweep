from sweepai.core.entities import FilesToChange

fcr = """Root cause:
The issue at hand is to provide a better user experience for first-time users by giving them an estimate of the time it will take to index their codebase. This is particularly important for larger codebases, where indexing can take a significant amount of time. The root cause of this issue is that the current implementation in `on_ticket.py` does not provide this feature.

Step-by-step thoughts with explanations:
* Thought 1: The first step is to determine the size of the repository. This can be done by using the GitHub API to get the total number of files in the repository.
* Thought 2: Once we have the number of files, we can estimate the time it will take to index the codebase. According to the issue description, indexing approximately 1000 files takes about 1 minute. We can use this as a baseline to estimate the indexing time for any given repository.
* Thought 3: After calculating the estimated time, we need to communicate this information to the user. This could be done through a prompt or a message that is displayed to the user when they first install Sweep.

<modify_file>
* sweepai/handlers/on_ticket.py: Add a function to estimate the indexing time based on the total number of files in the repository. This function should use the GitHub API to get the number of files, calculate the estimated time, and return this value. Then, in the main function that handles a new ticket, call this new function when the ticket is from a first-time user and display the estimated time to the user.
</create_file>
* None"""

ftc = FilesToChange.from_string(fcr)
