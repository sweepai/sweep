
<p align="center">
    <img src="https://github.com/sweepai/sweep/assets/26889185/39d500fc-9276-402c-9ec7-3e61f57ad233">
</p>
<p align="center">
    <i>Bug Reports & Feature Requests ⟶&nbsp; Code Changes</i>
</p>

<p align="center">
<a href="https://sweep.dev">
    <img alt="Landing Page" src="https://img.shields.io/badge/Site-sweep.dev-blue?link=https%3A%2F%2Fsweep.dev">
</a>
<a href="https://docs.sweep.dev/">
    <img alt="Docs" src="https://img.shields.io/badge/Docs-docs.sweep.dev-blue?link=https%3A%2F%2Fdocs.sweep.dev">
</a> 
<a href="https://discord.gg/sweep-ai">
    <img src="https://dcbadge.vercel.app/api/server/sweep-ai?style=flat" />
</a>
<img alt="PyPI" src="https://img.shields.io/pypi/v/sweepai">
<a href="https://pepy.tech/project/sweepai">
    <img src="https://static.pepy.tech/badge/sweepai/week" />
</a>
<a href="https://github.com/sweepai/sweep">
    <img src="https://img.shields.io/github/stars/sweepai/sweep" />
</a>
<a href="https://twitter.com/sweep__ai">
    <img src="https://img.shields.io/twitter/url?url=https%3A%2F%2Ftwitter.com%2Fsweep__ai" />
</a>
</p>

<b>Sweep</b> allows you to create and review GitHub issues with ease.
Simply describe any issue and Sweep will do the rest.
It will plan out what needs to be done, what changes to make, and write the changes to a PR. 

Supported languages: Python, Javascript/Typescript, Rust, Go, Java/C#, C++ and anything else GPT-4 supports

---

## ✨ Demo
For the best experience, [install Sweep](https://github.com/apps/sweep-ai) to one of your repos and see the magic happen.

[Demo](https://github.com/sweepai/sweep/assets/44910023/365ec29f-7317-40a7-9b5e-0af02f2b0e47)

## 🌠 Features
* Automatic interactive bug fixes & feature development
* PR auto self-review + comment handling (effectively [Reflexion](https://arxiv.org/abs/2303.11366))
* Address developer comments after PR is created using PR replies & code comments
* Code snippets embedding-based semantic & popularity search ([🔍 Rebuilding our Search Engine in a Day](https://docs.sweep.dev/how-we-rebuilt-our-code-search-engine-in-a-day))
* Chain-of-Thought retrieval using GPT Functions
* 🎊 New: Sweep Chat, a local interface for Sweep (see below)

## 🚀 Getting Started

### 🖥️ Sweep Chat
Sweep Chat allows you to interact with Sweep locally and will sync with GitHub. You can plan out your changes with Sweep, and then Sweep can create a pull request for you. 

1. Install [Sweep GitHub app](https://github.com/apps/sweep-ai) to desired repos

2. Run `pip install sweepai && sweep`. Note that you need python 3.10 or greater.

3. This should spin up a GitHub auth flow in your browser. Copy-paste the 🔵 blue 8-digit code from your terminal into the page. Then wait a few seconds and it should spin up Sweep Chat. You should only need to do the auth once.

4. Pick a repo from the dropdown at the top (the Github app must be installed on this repo). Then start chatting with Sweep Chat. Relevant searched files will show up on the right. Sweep Chat can make PRs if you ask it to create a PR. 
<img src="https://github.com/sweepai/sweep/blob/856ff66c2dbeaf39afbf6d8c49a620dfa70271fb/.assets/gradio-screenshot.png">

💡 You can force dark mode by going to http://127.0.0.1:7861/?__theme=dark.

#### From Source
If you want the nightly build and or if the latest build has issues.

1. `git clone https://github.com/sweepai/sweep && poetry install`
2. `python sweepai/app/cli.py`. Note that you need python 3.10 or greater.

### ✨ Sweep Github App
Setting up Sweep is as simple as adding the GitHub bot to a repo, then creating an issue for the bot to address.

1. Add the [Sweep GitHub app](https://github.com/apps/sweep-ai) to desired repos
2. Create new issue in repo, like "Sweep: Write tests"
3. "👀" means it is taking a look, and it will generate the desired code
4. "🚀" means the bot has finished its job and created a PR

## 🤝 Contributing
## GitHub Actions Setup

In this project, we use GitHub Actions for automated testing and continuous integration. GitHub Actions is a CI/CD platform that allows you to automate workflows directly from your GitHub repository. 

We have set up a workflow in the `.github/workflows/main.yml` file. This workflow is triggered on every push and pull request to the main branch. It sets up a Python environment, installs the necessary dependencies, and runs the tests.

By using GitHub Actions, we ensure that the tests are run in a consistent environment every time. It also allows us to catch any potential issues early before they are merged into the main branch.


Contributions are welcome and greatly appreciated! For detailed guidelines on how to contribute, please see the [CONTRIBUTING.md](CONTRIBUTING.md) file. In essence, you'll need to fork the repository, create a new branch for your feature or bug fix, commit your changes, and open a pull request.
For more detailed docs, see [🚀 Quickstart](https://docs.sweep.dev/start).

---

## 📘 Story

We were frustrated by small tickets, like simple bug fixes, annoying refactors, and small features, each task requiring us to open our IDE to fix simple bugs. So, we decided to leverage the capabilities of ChatGPT to address this directly in GitHub.

Unlike existing AI solutions, this can solve entire tickets and can be parallelized: developers can spin up 10 tickets and Sweep will address them all at once.

## 📚 The Stack
- GPT-4 32k 0613 (default) / Claude v1.3 100k
- ActiveLoop DeepLake for Vector DB with MiniLM L12 as our embeddings model
- Modal Labs for infra + deployment
- Gradio for Sweep Chat

## 🗺️ Roadmap
We're currently working on responding to linters and external search. For more, see [🗺️ Roadmap](https://docs.sweep.dev/roadmap).

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=sweepai/sweep&type=Date)](https://star-history.com/#sweepai/sweep&Date)

Consider starring us if you're using Sweep so more people hear about us!

---

<h2 align="center">
    Contributors
</h2>
<p align="center">
    Thank you for your contribution!
</p>
<p align="center">
    <a href="https://github.com/sweepai/sweep/graphs/contributors">
      <img src="https://contrib.rocks/image?repo=sweepai/sweep" />
    </a>
</p>
<p align="center">
    and, of course, Sweep!
</p>
<p align="center">
    <img src="https://github.com/sweepai/sweep/assets/26889185/39d500fc-9276-402c-9ec7-3e61f57ad233">
</p>
<p align="center">
    <i>Bug Reports & Feature Requests ⟶&nbsp; Code Changes</i>
</p>
...
<p align="center">
    and, of course, Sweep!
</p>
