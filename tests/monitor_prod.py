import os
import time

from github import Github

import sweepai.config.server  # NOQA

g = Github(os.environ.get("GITHUB_PAT"))
issue_url = "https://github.com/wwzeng1/landing-page/issues/206"
issue = g.get_repo("wwzeng1/landing-page").get_issue(206)

comment_id = list(issue.get_comments())[0].id

while True:
    comment = issue.get_comment(comment_id)
    body = comment.body
    start_time = time.time()
    print(f"Editing comment {comment_id}...")
    comment.edit(body=body.replace("- [ ] ↻ Restart Sweep", "- [x] ↻ Restart Sweep"))
    for i in range(60):
        comment = issue.get_comment(comment_id)
        print(f"Checking comment... ({time.time() - start_time:.2f})")
        if "- [ ] ↻ Restart Sweep" in comment.body:
            print(f"Got a response in {time.time() - start_time:.2f} seconds")
            break
        time.sleep(2)
    time.sleep(1)
