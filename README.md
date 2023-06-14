# Sweep

Sweep is a Github assistant bot that completes tickets by making a PR and responds to PR comments.

## Story

We were frustrated by small tickets such simple bug fixes, annoying refactors and small features and realized ChatGPT/GPT-4 could easily do it. Unlike copilot, this can solve entire tickets and can be parallelized: someone can spin up 10 tickets and have it solve them all at once. 

## Setup

To set up the project, follow these steps:

1. Clone the repository
2. Install poetry using `pip install poetry`
3. Install the dependencies using `poetry install`
4. Set up your environment variables in a `.env` file. You will need to set the following variables:
    - `BOT_TOKEN`: Your Github bot token
    - `OPENAI_SECRET`: Your OpenAI API secret key
5. Run the bot using `modal serve src/api.py` and add the endpoint URL to the repo webhooks.
6. (Optional) Index your codebase and relevant documents into Jina

## Tools
- Modal
- OpenAI
- PyGithub
- Jina

## Usage

Once the bot is running, it will listen for new issues by creating a PR and will respond to PR comments, being aware of the line numbers.
