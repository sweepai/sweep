from github import Github

class GithubRepo:
    def __init__(self, github: Github, repo_name: str):
        self.repo = github.get_repo(repo_name)

    def get_primary_language(self):
        return self.repo.language