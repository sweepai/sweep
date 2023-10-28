from github import Github


def extract_method(snippet, file_path, method_name, project_name):
    return "test result"


def get_jwt():
    return "test jwt"


def get_token(installation_id):
    return "test token"


def get_github_client(installation_id):
    token = "test token"
    client = Github(token)
    return token, client


def get_installation_id(username):
    return "test installation id"


def make_valid_string(string):
    return string


def get_hunks(a, b, context):
    return "test hunks"


class ClonedRepo:
    def __init__(self, repo_full_name, installation_id, branch, token):
        self.repo_full_name = repo_full_name
        self.installation_id = installation_id
        self.branch = branch
        self.token = token
