from sweepai.repo import GithubRepo

def create_issue(repo: GithubRepo, title: str, body: str):
    repo.create_issue(f'Sweep: {title}', body)