import os
from github import Github

def calculate_issue_quality(issue):
    """
    Calculate the quality of an issue based on the length of its title and body.

    Parameters:
    issue (github.Issue.Issue): The issue to calculate the quality of.

    Returns:
    int: The quality score of the issue.
    """
    title_length = len(issue.title)
    body_length = len(issue.body)
    quality_score = title_length + body_length
    return quality_score

if __name__ == "__main__":
    access_token = os.environ.get("ACCESS_TOKEN")
    g = Github(access_token)
    repo = g.get_repo("sweepai/sweep")
    issue = repo.get_issue(number=1)  # Replace with actual issue number
    quality_score = calculate_issue_quality(issue)
    print(f"Quality score: {quality_score}")