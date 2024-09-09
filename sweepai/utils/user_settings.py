import traceback

from loguru import logger
import resend
from github import Github
from github.AppAuthentication import AppAuthentication
from pydantic import BaseModel

from sweepai.config.server import (
    GITHUB_APP_ID,
    GITHUB_APP_PEM,
    IS_SELF_HOSTED,
    PROGRESS_BASE_URL,
    RESEND_API_KEY,
)
from sweepai.utils.chat_logger import global_mongo_client
from sweepai.utils.github_utils import get_installation_id

resend.api_key = RESEND_API_KEY


class UserSettings(BaseModel):
    username: str
    email: str = ""
    do_email: bool = True

    @classmethod
    def from_username(
        cls, username: str, installation_id: int = None
    ) -> "UserSettings":
        if IS_SELF_HOSTED:
            return cls(username=username, email="", do_email=False)

        db = global_mongo_client["users"]
        collection = db["users"]

        doc = collection.find_one({"username": username})

        if doc is None:
            # Try get email from github

            try:
                installation_id = get_installation_id(username)
                auth = AppAuthentication(
                    installation_id=installation_id,
                    app_id=GITHUB_APP_ID,
                    private_key=GITHUB_APP_PEM,
                )
                g = Github(app_auth=auth)
                email = (
                    g.get_user(username).email or ""
                )  # Some user's have private emails
            except Exception as e:
                logger.error(
                    str(e)
                    + "\n\n"
                    + traceback.format_exc()
                    + f"\n\nUsername: {username}"
                )
                email = ""
            return UserSettings(username=username, email=email)

        return cls(**doc)

    def get_message(self, completed: bool = False) -> str:
        # This is a message displayed to the user in the ticket
        if self.email and self.do_email:
            return f"> [!TIP]\n> I'll email you at {self.email} when I complete this pull request!"
        elif not self.email:
            if not completed:
                return f"> [!TIP]\n> I can email you when I complete this pull request if you set up your email [here]({PROGRESS_BASE_URL}/profile)!"
            else:
                return f"> [!TIP]\n> I can email you next time I complete a pull request if you set up your email [here]({PROGRESS_BASE_URL}/profile)!"

    def send_email(
        self,
        subject: str,
        html: str,
    ):
        if self.email and self.do_email and RESEND_API_KEY is not None:
            return resend.Emails.send(
                {
                    "from": "Sweep Alerts <notifications@sweep.dev>",
                    "to": self.email,
                    "subject": subject,
                    "html": html,
                }
            )


if __name__ == "__main__":
    print(UserSettings.from_username("kevinlu1248").send_email("test", "test"))
