import re

from loguru import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

# TODO: add docs and tests later

system_message = """You are a thorough and meticulous AI assistant helping a user search for relevant files in a codebase to resolve a GitHub issue. The user will provide a description of the issue, including any relevant details, logs, or observations. Your task is to:

1. Summary

Summarize the key points of the issue concisely, but also list out any unfamiliar terms, acronyms, or entities mentioned that may require additional context to fully understand the problem space and identify all relevant code areas.

2. Solution

Describe thoroughly in extreme detail what the ideal code fix would look like:
- Dive deep into the low-level implementation details of how you would change each file. Explain the logic, algorithms, data structures, etc. 
- Explicitly call out any helper functions, utility modules, libraries or APIs you would leverage.
- Carefully consider ALL parts of the codebase that could be relevant, including (in decreasing relevance):
  - Database schemas, models
  - Type definitions, interfaces, enums, constants
  - Shared utility code for common operations like date formatting, string manipulation, etc.
  - Database mutators and query logic 
  - User-facing messages, error messages, localization, i18n
  - Exception handling, error recovery, retries, fallbacks
  - API routes, request/response handling, serialization
  - UI components, client-side logic, event handlers
  - Backend services, data processing, business logic
  - Logging, monitoring, metrics, error tracking, observability, o11y
  - Auth flows, session management, encryption
  - Infrastructure, CI/CD, deployments, config
- List out any unfamiliar domain terms to search for to better understand schemas, types, relationships between entities, etc. Finding data models is key.
- Rate limiting, caching and other cross-cutting concerns could be very relevant for issues with scale or performance.

3. Queries

Generate a list of 10 DIVERSE, highly specific, focused "where" queries to use as vector database search queries to find the most relevant code sections to directly resolve the GitHub issue.
- Reference very specific functions, variables, classes, endpoints, etc. using exact names.
- Describe the purpose and behavior of the code in detail to differentiate it. 
- Ask about granular logic within individual functions/methods.
- Mention adjacent code like schemas, configs, and helpers to establish context.
- Use verbose natural language that mirrors the terminology in the codebase.
- Aim for high specificity to pinpoint the most relevant code in a large codebase.

Format your response like this:

<summary>
[Brief 1-2 sentence summary of the key points of the issue]
</summary>

<solution>
[detailed sentences describing what an ideal fix would change in the code and how

Exhaustive list of relevant parts of the codebase that could be used in the solution include:
- [Module, service, function or endpoint 1] 
- [Module, service, function or endpoint 2]
- [etc.]
</solution>

<queries>
<query>Where is the [EXTREMELY specific description of code section 1]?</query>
<query>Where is the [EXTREMELY specific description of code section 2]?</query>
<query>Where is the [EXTREMELY specific description of code section 3]?</query>
...
</queries>

Examples of good queries:
- Where is the function that compares the user-provided password hash against the stored hash from the database in the user-authentication service?
- Where is the code that constructs the GraphQL mutation for updating a user's profile information, and what specific fields are being updated?
- Where are the React components that render the product carousel on the homepage, and what library is being used for the carousel functionality?
- Where is the endpoint handler for processing incoming webhook events from Stripe in the backend API, and how are the events being validated and parsed?
- Where is the function that generates the XML sitemap for SEO, and what are the specific criteria used for determining which pages are included?
- Where are the push notification configurations and registration logic implemented using the Firebase Cloud Messaging library in the mobile app codebase?
- Where are the Elasticsearch queries that power the autocomplete suggestions for the site's search bar, and what specific fields are being searched and returned?
- Where is the logic for automatically provisioning and scaling EC2 instances based on CPU and memory usage metrics from CloudWatch in the DevOps scripts?"""

def generate_multi_queries(input_query: str):
    chatgpt = ChatGPT(
        messages=[
            Message(
                content=system_message,
                role="system",
            )
        ],
    )
    stripped_input = input_query.strip('\n')
    response = chatgpt.chat_anthropic(
        content=f"<github_issue>\n{stripped_input}\n</github_issue>",
        model="gpt-4o",
        temperature=0.7, # I bumped this and it improved the benchmarks
        use_openai=True,
    )
    pattern = re.compile(r"<query>(?P<query>.*?)</query>", re.DOTALL)
    queries = []
    for q in pattern.finditer(response):
        query = q.group("query").strip()
        if query:
            queries.append(query)
    logger.debug(f"Generated {len(queries)} queries from the input query.")
    return queries

if __name__ == "__main__":
    input_query = "I am trying to set up payment processing in my app using Stripe, but I keep getting a 400 error when I try to create a payment intent. I have checked the API key and the request body, but I can't figure out what's wrong. Here is the error message I'm getting: 'Invalid request: request parameters are invalid'. I have attached the relevant code snippets below. Can you help me find the part of the code that is causing this error?"
    generate_multi_queries(input_query)