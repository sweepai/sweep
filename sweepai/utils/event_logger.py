import os
from loguru import logger
import highlight_io
from posthog import Posthog

POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY")
if POSTHOG_API_KEY is None:
    posthog = None
else:
    posthog = Posthog(project_api_key=POSTHOG_API_KEY, host="https://app.posthog.com")
HIGHLIGHT_API_KEY = os.environ.get("HIGHLIGHT_API_KEY")
if HIGHLIGHT_API_KEY is None:
    H = None
else:
    H = highlight_io.H(HIGHLIGHT_API_KEY)
    logger.add(
        H.logging_handler,
        format="{message}",
        level="INFO",
        backtrace=True,
    )
