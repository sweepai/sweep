import os
import time
from github import Github
from prometheus_client import Histogram, start_http_server

# Prometheus Metrics
response_time_histogram = Histogram('github_response_time', 'Time taken for GitHub response')

# GitHub API setup
g = Github(os.environ.get("GITHUB_PAT"))
issue_url = "https://github.com/wwzeng1/landing-page/issues/206"
issue = g.get_repo("wwzeng1/landing-page").get_issue(206)
comment_id = list(issue.get_comments())[0].id

# Start the Prometheus server
# NOTE: docker run --name prometheus -d -p 127.0.0.1:9090:9090 prom/prometheus
start_http_server(8009)

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
            response_time = time.time() - start_time
            print(f"Got a response in {response_time:.2f} seconds")
            response_time_histogram.observe(response_time)
            break
        time.sleep(2)
    time.sleep(10)
