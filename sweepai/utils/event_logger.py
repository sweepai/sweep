import highlight_io
from loguru import logger
from posthog import Posthog

from sweepai.utils.config.server import POSTHOG_API_KEY, HIGHLIGHT_API_KEY

if POSTHOG_API_KEY is None:
    posthog = Posthog(project_api_key="none", disabled=True, host='https://app.posthog.com')
    logger.warning("Initialized an empty Posthog instance as POSTHOG_API_KEY is not present.")
else:
    posthog = Posthog(project_api_key=POSTHOG_API_KEY, host='https://app.posthog.com')

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
