import os

import openai

from sweepai.core.external_searcher import ExternalSearcher

openai.api_key = os.environ.get("OPENAI_API_KEY")

problem = """
## Sweep: Scaffold tests in generated SDK

We recently introduced simple test scaffolding in [fern-python](https://github.com/fern-api/fern-python/pull/296). We should do something similar here, potentially with `jest`.

Previous PR:

This adds pytest to the list of dev dependencies, as well as creates a tests/ directory with a simple no-op test.

The generated test includes the syntax required for skipping tests (via @pytest.mark.skip) to demonstrate the pytest import. We also include a link to the pytest docs for the user to learn more.
"""

print(ExternalSearcher.extract_summaries(problem))
