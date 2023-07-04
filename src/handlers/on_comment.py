def send_simple_response(user_comment, github_repo):
    """
    Sends a simple response to the user's comment using the pygithub library.

    Args:
        user_comment (str): The user's comment.
        github_repo (GithubRepo): The Github repository.
    """
    # Use the pygithub library to send the response
    response = github_repo.create_issue_comment(user_comment)
    if response:
        logger.info(f"Response sent: {response}")
    else:
        logger.error("Failed to send response")
    # TODO: Replace with actual code to send the response

def on_comment(
    repo_full_name: str,
    repo_description: str,
    comment: str,
    pr_path: str | None,
    pr_line_position: int | None,
    username: str,
    installation_id: int,
    pr_number: int = None,
):
    # Existing code...

    # Call the new send_simple_response method
    try:
        response = send_simple_response(comment, repo)
        if not response:
            raise Exception("Failed to send response")
    except Exception as e:
        logger.error(f"Failed to send response: {e}")

