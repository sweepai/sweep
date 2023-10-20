from posthog import Posthog

from sweepai.config.server import POSTHOG_API_KEY
from sweepai.logn import logger

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
