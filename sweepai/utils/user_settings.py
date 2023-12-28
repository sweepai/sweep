from chat_logger import global_mongo_client
from github import Github
from github.AppAuthentication import AppAuthentication
from pydantic import BaseModel

from sweepai.config.server import GITHUB_APP_ID, GITHUB_APP_PEM
from sweepai.utils.github_utils import get_installation_id


class UserSettings(BaseModel):
    username: str
    email: str
    do_email: bool = True

    @classmethod
    def from_username(cls, username: str, installation_id: int = None):
        db = global_mongo_client["users"]
        collection = db["users"]

        doc = collection.find_one({"username": username})

        if doc is None:
            # Try get email from github
            installation_id = get_installation_id(username)
            auth = AppAuthentication(
                installation_id=installation_id,
                app_id=GITHUB_APP_ID,
                private_key=GITHUB_APP_PEM,
            )
            g = Github(app_auth=auth)
            email = g.get_user(username).email or ""  # Some user's have private emails
            return UserSettings(username=username, email=email)

        return cls(**doc)


if __name__ == "__main__":
    print(UserSettings.from_username("wwzeng1"))
