# import os
# import loguru
# from logtail import LogtailHandler
# import logging
from logn import logger

# import loguru
# from loguru import logger
from posthog import Posthog
import highlight_io

from sweepai.config.server import POSTHOG_API_KEY, HIGHLIGHT_API_KEY, LOGTAIL_SOURCE_KEY

if POSTHOG_API_KEY is None or POSTHOG_API_KEY.lower() == "none":
    posthog = Posthog(
        project_api_key="none", disabled=True, host="https://app.posthog.com"
    )
    logger.warning(
        "Initialized an empty Posthog instance as POSTHOG_API_KEY is not present."
    )
else:
    posthog = Posthog(project_api_key=POSTHOG_API_KEY, host="https://app.posthog.com")

# if LOGTAIL_SOURCE_KEY:
#     logger = logger.bind(pid=os.getpid())
#     handler = LogtailHandler(source_token=LOGTAIL_SOURCE_KEY)
#     logger.add(handler)
#     logger.info("Initialized LogtailHandler")


def set_highlight_id(id):
    if HIGHLIGHT_API_KEY is not None:
        H = highlight_io.H(
            HIGHLIGHT_API_KEY,
            instrument_logging=False,
        )

        """
        logger.add(
            H.logging_handler,
            format=str(id) + " {message}",
            level="INFO",
            backtrace=True,
            serialize=True,
        )
        """
