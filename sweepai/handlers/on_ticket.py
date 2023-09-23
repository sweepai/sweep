            # Calculate is_python_issue
            is_python_issue = sum([not file_path.endswith(".py") for file_path in file_paths]) < 2
            logger.info(f"IS PYTHON ISSUE: {is_python_issue}")
            
            # Log is_python_issue as an event to posthog
            posthog.capture('is_python_issue', {'value': is_python_issue})
            
            current_issue.edit(
                body=summary + "\n\n---\n\nChecklist:\n\n" + subissues_checklist
            )
            edit_sweep_comment(
                f"I finished creating the subissues! Track them at:\n\n"
                + "\n".join(f"* #{subissue.issue_id}" for subissue in subissues),
                3,
                done=True,
            )
            edit_sweep_comment(f"N/A", 4)