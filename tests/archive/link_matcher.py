import re

def extract_links(text):
    pattern = r'\b(?:(?:https?|ftp)://|www\.)\S+\b'
    return list(set(re.findall(pattern, text)))

# Example usage:
text = """
We recently introduced simple test scaffolding in [fern-python](https://github.com/fern-api/fern-python/pull/296). We should do something similar here, potentially with `jest`.

Previous PR:

This adds pytest to the list of dev dependencies, as well as creates a tests/ directory with a simple no-op test.

The generated test includes the syntax required for skipping tests (via @pytest.mark.skip) to demonstrate the pytest import. We also include a link to the pytest docs for the user to learn more.
"""
links = extract_links(text)
print(links)
