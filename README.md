
# :broom: Sweep

Sweep is a Github assistant bot that solves tickets by writing a PR.

## 📚 Story

We were frustrated by small tickets such as simple bug fixes, annoying refactors and small features that could just be fed to ChatGPT. So we fed it to ChatGPT.

Unlike copilot, this can solve entire tickets and can be parallelized: someone can spin up 10 tickets and have it solve them all at once. 

## 📚 How to Use

To use Sweep, first install the app on your Github repository. Once installed, you can create issues with the prefix "Sweep:" followed by the task you want the bot to perform. For example, "Sweep: Write tests". The bot will then take a look at the issue (indicated by the eyes emoji) and start working on it. Once it's done, it will mark the issue with a rocket emoji.

## 🚀 Quickstart
Install at https://github.com/apps/sweep-ai, add your repo, and make an issue such as "Sweep: Write tests" (need the prefix). Eyes :eyes: means it's taking a look and rocket 🚀 means it's done. For more detailed docs, see [🚀 Quickstart](https://docs.sweep.dev/start).

### For the slack addon:

0. Ensure the Sweep GitHub app is installed. For the rest of this guide, we will call the target repository’s full name {repo} (like org_name/repo_name, ex: sweepai/sweep).

1. [Install our slackbot](https://sweepai--prod-slack-bot.modal.run)

2. Make a new channel
Set the description to “Sweep for {repo}”. It will not work without this. This channel will only serve {repo}.

3. Make a slash command
Type a command like “/sweep Write a unit test“.

## The Stack
- GPT-4 32k 0613 (default) / Claude v1.3 100k
- ActiveLoop DeepLake for Vector DB with MiniLM L12 as our embeddings model
- Modal Labs for infra + deployment

## 🌠 Features

* Vector search using DeepLake - This feature allows the bot to perform a vector search using DeepLake, a powerful vector database.
* CoT internal search using GPT Functions - This feature enables the bot to perform an internal search using GPT Functions.
* Issue comment reply handling - This feature allows the bot to handle replies to issue comments.
* PR auto self-review + comment handling - This feature enables the bot to automatically review its own PRs and handle comments.

## 🌠 Features
* Vector search using DeepLake
* CoT internal search using GPT Functions
* Issue comment reply handling
* PR auto self-review + comment handling (effectively Reflexion https://arxiv.org/abs/2303.11366)

## 📚 Requirements

To use Sweep, you need to have a Github account and at least one repository where you can install the bot. You also need to have the necessary permissions to install apps on your repository.

## 🗺️ Roadmap
We're currently working on responding to linters and external search. For more, see [🗺️ Roadmap](https://docs.sweep.dev/roadmap).

## 🚀 Quickstart

1. Install Sweep at https://github.com/apps/sweep-ai and add your repository.
2. Create an issue with the prefix "Sweep:" followed by the task you want the bot to perform.
3. Wait for the bot to take a look at the issue and start working on it.
4. Once the bot is done, it will mark the issue with a rocket emoji.

For more detailed docs, see [🚀 Quickstart](https://docs.sweep.dev/start).

