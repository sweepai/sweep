# These are the docs that we index for Sweep.
# We scrape these docs once a day and store them in our database.
# You can use it by adding the key to your GitHub issue.
# Example: Use PyGitHub to get the number of files in a repo.

# The title should be restrictive so it only shows up when the user wants it.
# "React JS" is good, "React" is not.
# The url should be the root of the docs, not a specific page. We will scrape all pages under this root.
# "https://react.dev/" is good, "https://react.dev/docs/getting-started" is not.
# Write a natural language description of what the package is and how it's used to help Sweep.

DOCS_ENDPOINTS = {
    "Modal Labs": (
        "https://modal.com/docs/guide",
        "Modal is a platform for building and deploying serverless applications.",
    ),
    "Llama Index": (
        "https://gpt-index.readthedocs.io/en/latest/",
        "Llama Index is a framework for allowing large language models to use external context.",
    ),
    "Llama Index TS": (
        "https://ts.llamaindex.ai/",
        "Llama Index is a framework for allowing large language models to use external context.",
    ),
    "Langchain": (
        "https://python.langchain.com/docs/",
        "Langchain is a framework for building and deploying apps using large language models.",
    ),
    "Langchain JS": (
        "https://js.langchain.com/docs/",
        "Langchain is a framework for building and deploying apps using large language models.",
    ),
    "React JS": (
        "https://react.dev/",
        "React is a JavaScript library for building user interfaces.",
    ),
    "Docusaurus": (
        "https://docusaurus.io/docs",
        "Docusaurus is a modern static website generator.",
    ),
    "OpenAI": (
        "https://platform.openai.com/docs/",
        "OpenAI is a client for the OpenAI API.",
    ),
    "PyGitHub": (
        "https://pygitlab.readthedocs.io/en/stable/",
        "PyGitLab is a client for the GitLab API.",
    ),
    "Laravel": (
    "Django": (
        "https://django.readthedocs.io/en/stable/",
        "Django is a Python framework for building web apps.",
    ),
    "Django Rest Framework": (
        "https://www.django-rest-framework.org",
        "Django Rest Framework is a Python framework for building REST APIs.",
    ),
    "Celery": (
        "https://docs.celeryq.dev/en/stable/",
        "Celery is a Python framework for building distributed task queues.",
    ),
    "NumPy": (
        "https://numpy.org/doc/stable/",
        "NumPy is a Python library for scientific computing.",
    ),


    "React JS": (
        "https://react.dev/",
        "React is a JavaScript library for building user interfaces.",
    ),

}
    "Django": (
        "https://django.readthedocs.io/en/stable/",
        "Django is a Python framework for building web apps.",
    ),
    "Django Rest Framework": (
        "https://www.django-rest-framework.org",
        "Django Rest Framework is a Python framework for building REST APIs.",
    ),
    "Celery": (
        "https://docs.celeryq.dev/en/stable/",
        "Celery is a Python framework for building distributed task queues.",
    ),
    "NumPy": (
        "https://numpy.org/doc/stable/",
        "NumPy is a Python library for scientific computing.",
    ),
    "Jest": ("https://jestjs.io/", "Jest is a JavaScript testing framework."),
    "Nucypher TS": (
        "https://gitlab.com/nucypher/nucypher-ts",
        "NuCypher is a TypeScript library for building privacy-preserving applications.",
    ),
    "NuCypher": (
        "https://github.com/nucypher/nucypher",
        "NuCypher is a Python library for building privacy-preserving applications.",
    ),
    "Stripe": (
        "https://docs.stripe.com/",
        "Stripe is a platform used to help companies accept payments, send payouts, automate financial processes, and grow revenue.",
    ),

}
        "https://laravel.com/docs",
        "Laravel is a PHP framework for building web apps.",

    "Nucypher TS": (
        "https://gitlab.com/nucypher/nucypher-ts",
        "NuCypher is a TypeScript library for building privacy-preserving applications.",
    ),
    "NuCypher": (
        "https://github.com/nucypher/nucypher",
        "NuCypher is a Python library for building privacy-preserving applications.",
    ),
    "Stripe": (
        "https://docs.stripe.com/",
        "Stripe is a platform used to help companies accept payments, send payouts, automate financial processes, and grow revenue.",
    ),
}

if __name__ == "__main__":
    for title, (url, description) in DOCS_ENDPOINTS.items():
        assert title, f"Title for {url} must not be empty"
        assert url.startswith("http"), f"URL {url} must start with http"
        assert description, f"Description for {title} must not be empty"
    print(f"Found {len(DOCS_ENDPOINTS)} docs.")
