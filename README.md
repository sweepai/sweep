# :broom: Sweep

Sweep is a Github assistant bot that solves tickets by writing a PR.

## 📚 Story

We were frustrated by small tickets such as simple bug fixes, annoying refactors and small features that could just be fed to ChatGPT. So we fed it to ChatGPT.

Unlike copilot, this can solve entire tickets and can be parallelized: someone can spin up 10 tickets and have it solve them all at once. 

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
* Vector search using DeepLake
* CoT internal search using GPT Functions
* Issue comment reply handling
* PR auto self-review + comment handling (effectively Reflexion https://arxiv.org/abs/2303.11366)

## 🗺️ Roadmap
We're currently working on responding to linters and external search. For more, see [🗺️ Roadmap](https://docs.sweep.dev/roadmap).
