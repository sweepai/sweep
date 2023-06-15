# :broom: Sweep

Sweep is a Github assistant bot that solves tickets by writing a PR.

## 📚 Story

We were frustrated by small tickets such as simple bug fixes, annoying refactors and small features that could just be fed to ChatGPT. So we fed it to ChatGPT.

Unlike copilot, this can solve entire tickets and can be parallelized: someone can spin up 10 tickets and have it solve them all at once. 

## The Stack
- GPT-4 32k 0613 (default) / Claude v1.3 100k
- ActiveLoop DeepLake for Vector DB with MiniLM L12 as our embeddings model
- Modal Labs for infra + deployment

## 🚀 Quickstart
Install at https://github.com/apps/sweep-ai, add your repo, and make an issue such as "Sweep: Write tests" (need the prefix). Eyes :eyes: means it's taking a look and rocket 🚀 means it's done. For more detailed docs, see [🚀 Quickstart](https://docs.sweep.dev/start).

## 🌠 Features
* Vector search using DeepLake
* CoT internal search using GPT Functions
* Issue comment reply handling
* PR auto self-review + comment handling (effectively Reflexion https://arxiv.org/abs/2303.11366)

## 🗺️ Roadmap
We're currently working on responding to linters and external search. For more, see [🗺️ Roadmap](https://docs.sweep.dev/roadmap).
