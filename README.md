# Sweep

Sweep is a Github assistant bot that helps with issue and pull request management. 

## Setup

To set up the project, follow these steps:

1. Clone the repository
2. Install poetry using `pip install poetry`
3. Install the dependencies using `poetry install`
4. Set up your environment variables in a `.env` file. You will need to set the following variables:
    - `BOT_TOKEN`: Your Github bot token
    - `OPENAI_SECRET`: Your OpenAI API secret key
5. Run the bot using `poetry run python src/main.py`

## Usage

Once the bot is running, it will listen for new issues and pull requests. When a new issue or pull request is created, the bot will automatically assign it to the appropriate team member based on the issue or pull request's labels.
