import re
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

# TODO: add docs and tests later

system_message = """You are an AI assistant helping a user search for relevant files in a codebase to resolve a GitHub issue. The user will provide a description of the issue, including any relevant details, logs, or observations. Your task is to:

1. Summarize the key points of the issue in 1-2 sentences. 

2. Describe in detail what the ideal code fix would look like:
- List each file that would need to be changed
- Explain in extreme detail how you would modify each file 
- Mention any helper functions or utility code you would use
- List all the relevant parts of a well-organized codebase that could be edited or imported in the solution, choosing only applicable items from this list in decreasing priority order:
  - Type definitions, interfaces, enums 
  - Utility functions, helper classes (for dates, strings, math, etc.)
  - Database schema, model definitions
  - API endpoint handlers
  - Frontend components, views
  - Backend services, controllers 
  - Internationalization copy, user-facing messages
  - Observability, monitoring, logging configuration 
  - Authentication, authorization logic
  - Infrastructure as code, deployment scripts
  - Environment variables, configuration settings

3. Generate a list of 15 highly specific, focused "where" queries to use as vector database search queries to find the most relevant code sections to directly resolve the GitHub issue. 
- Reference specific functions, methods, schemas, types, API calls, libraries, design patterns, constants, variables or settings from the issue that may be causing the problem
- Ask about the precise location of code responsible for the problematic actions or processes described
- Use exact terminology and add descriptive details to pinpoint the relevant code
- Ensure queries are semantically similar to the code, in the format "Where is function f that does x with y to accomplish z from module Foo relating to Bar" 
- Make queries extremely specific to sections of individual functions, methods or classes, since the codebase is large

Format your response like this:
<summary>
[Brief 1-2 sentence summary of the key points of the issue]
</summary>

<solution>
[1-2 sentences describing what an ideal fix would change in the code and how] Relevant parts of the codebase that could be used in the solution include:
- [Module, service, function or endpoint 1] 
- [Module, service, function or endpoint 2]
- [etc.]
</solution>

<queries>
<query>Where is the [extremely specific description of code section 1]?</query>
<query>Where is the [extremely specific description of code section 2]?</query>
<query>Where is the [extremely specific description of code section 3]?</query>
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
        f"<github_issue>\n{stripped_input}\n</github_issue>", 
        model="claude-3-opus-20240229"
    )
    pattern = re.compile(r"<query>(?P<query>.*?)</query>", re.DOTALL)
    queries = []
    for q in pattern.finditer(response):
        query = q.group("query").strip()
        if query:
            queries.append(query)
    breakpoint()
    return queries

if __name__ == "__main__":
    input_query = "I am trying to set up payment processing in my app using Stripe, but I keep getting a 400 error when I try to create a payment intent. I have checked the API key and the request body, but I can't figure out what's wrong. Here is the error message I'm getting: 'Invalid request: request parameters are invalid'. I have attached the relevant code snippets below. Can you help me find the part of the code that is causing this error?"
    generate_multi_queries(input_query)
