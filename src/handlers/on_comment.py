# Check if the comment is "REVERT"
    if comment.strip().upper() == "REVERT":
        rollback_file(repo_full_name, pr_path, installation_id, pr_number)
        return {"success": True, "message": "File has been reverted to the previous commit."}

    # Check if the PR is closed
    if pr.state == "closed":
        return {"success": True, "message": "The PR is closed. No action was performed."}

