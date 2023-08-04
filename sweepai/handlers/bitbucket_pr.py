from bitbucket.client import Client
from sweepai.core.entities import FileChangeRequest, PullRequest
from sweepai.utils.config.server import BITBUCKET_APP_ID, BITBUCKET_APP_SECRET
from sweepai.handlers.create_pr import GitHostingService

class BitbucketService(GitHostingService):
    def __init__(self):
        self.client = Client(BITBUCKET_APP_ID, BITBUCKET_APP_SECRET)

    def create_branch(self, branch_name: str):
        # Implement the method to create a branch using Bitbucket's API
        pass

    def change_files(self, file_change_requests: list[FileChangeRequest], branch_name: str):
        # Implement the method to change files using Bitbucket's API
        pass

    def create_pull_request(self, title: str, body: str, head: str, base: str):
        # Implement the method to create a pull request using Bitbucket's API
        pass