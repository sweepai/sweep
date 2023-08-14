# These are the docs that we index for Sweep.
# We scrape these docs once a day and store them in our database.
# You can use it by adding the key to your GitHub issue.
# Example: Use PyGitHub to get the number of files in a repo.

# The title should be restrictive so it only shows up when the user wants it. 
# "React JS" is good, "React" is not.
# The url should be the root of the docs, not a specific page. We will scrape all pages under this root.
# "https://react.dev/" is good, "https://react.dev/docs/getting-started" is not.

DOCS_ENDPOINTS = {
  "Modal Labs": "https://modal.com/docs/guide",
  "Llama Index": "https://gpt-index.readthedocs.io/en/latest/",
  "Llama Index TS": "https://ts.llamaindex.ai/",
  "Langchain": "https://python.langchain.com/docs/",
  "Langchain JS": "https://js.langchain.com/docs/",
  "React JS": "https://react.dev/",
  "Docusaurus": "https://docusaurus.io/docs",
  "OpenAI": "https://platform.openai.com/docs/",
  "Anthropic": "https://docs.anthropic.com/claude/docs",
  "PyGitHub": "https://pygithub.readthedocs.io/en/stable/",
  "Laravel": "https://laravel.com/docs",
  "Django": "https://django.readthedocs.io/en/stable/",
  "Django Rest Framework": "https://www.django-rest-framework.org",
  "Celery": "https://docs.celeryq.dev/en/stable/",
  "NumPy": "https://numpy.org/doc/stable/",
  "Jest": "https://jestjs.io/",
  "Nucypher TS": "https://github.com/nucypher/nucypher-ts",
  "NuCypher": "https://github.com/nucypher/nucypher"
}
