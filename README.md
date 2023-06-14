# :broom: Sweep

Sweep is a Github assistant bot that solves tickets by writing a PR.

## Story

We were frustrated by small tickets such as simple bug fixes, annoying refactors and small features that could just be fed to ChatGPT. So we fed it to ChatGPT.

Unlike copilot, this can solve entire tickets and can be parallelized: someone can spin up 10 tickets and have it solve them all at once. 

## The Stack
- GPT-4 32k 0613 (default) / Claude v1.3 100k
- ActiveLoop DeepLake for Vector DB with MiniLM L12 as our embeddings model
- Modal Labs for infra + deployment

## Installation
Install at https://github.com/apps/sweep-ai, add your repo, and make a Github issue such as "Sweep: Write tests" (need the prefix). Eyes 👀 means Sweep's taking a look and rocket 🚀 means it's done. 

## Roadmap
* External search (Anthropic docs, as GPT 3.5/4 is trained on pre-2019)
* CLI access ("install puppeteer" or "fix all mypy type-check errors")
* Deleting old Sweep branches / PRs to declutter
* `sweep.toml` configuration file
