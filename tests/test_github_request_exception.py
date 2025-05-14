from sweepai.utils.github_utils import get_token
import os
from github import Github
from github.Auth import Token
# get default_base_url from github
from github.Requester import Requester
from github.GithubException import BadCredentialsException, UnknownObjectException

class CustomRequester(Requester):
    def __init__(self, token, timeout=15, user_agent="PyGithub/Python", per_page=30, verify=True, retry=True, pool_size=None, installation_id=None):
        self.token = token
        self.installation_id = installation_id
        base_url = "https://api.github.com"
        auth = Token(token)
        super().__init__(auth=auth, base_url=base_url, timeout=timeout, user_agent=user_agent, per_page=per_page, verify=verify, retry=retry, pool_size=pool_size)

    def _refresh_token(self):
        self.token = get_token(self.installation_id)
        self._Requester__authorizationHeader = f"token {self.token}"

    def requestJsonAndCheck(self, *args, **kwargs):
        try:
            breakpoint() # test breakpoint to ensure it refreshes credentials
            raise BadCredentialsException(status=401, data={"message": "Bad credentials"})
            return super().requestJsonAndCheck(*args, **kwargs)
        except (BadCredentialsException, UnknownObjectException):
            self._refresh_token()
            return super().requestJsonAndCheck(*args, **kwargs)

class CustomGithub(Github):
    def __init__(self, installation_id: int, *args, **kwargs):
        self.installation_id = installation_id
        self.token = self._get_token()
        super().__init__(self.token, *args, **kwargs)
        self._Github__requester = CustomRequester(self.token, installation_id=self.installation_id)

    def _get_token(self) -> str:
        if not self.installation_id:
            return os.environ["GITHUB_PAT"]
        return get_token(self.installation_id)

def get_github_client(installation_id: int) -> tuple[str, CustomGithub]:
    github_instance = CustomGithub(installation_id)
    return github_instance.token, github_instance

installation_id = None
user_token, g = get_github_client(installation_id)
repo = g.get_repo("sweepai/sweep")