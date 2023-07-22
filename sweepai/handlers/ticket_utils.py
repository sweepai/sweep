def fetch_files(sweep_bot):
    """
    Fetches files to modify/create.
    """
    logger.info("Fetching files to modify/create...")
    file_change_requests, create_thoughts, modify_thoughts = sweep_bot.get_files_to_change()
    return file_change_requests, create_thoughts, modify_thoughts

def generate_pr(sweep_bot):
    """
    Generates a PR.
    """
    logger.info("Generating PR...")
    pull_request = sweep_bot.generate_pull_request()
    return pull_request

def make_pr(file_change_requests, pull_request, sweep_bot, username, installation_id, issue_number):
    """
    Makes a PR.
    """
    logger.info("Making PR...")
    response = create_pr(file_change_requests, pull_request, sweep_bot, username, installation_id, issue_number)
    return response

def handle_exceptions(e):
    """
    Handles exceptions.
    """
    logger.error(f"An error occurred: {e}")
    raise e