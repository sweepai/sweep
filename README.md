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
    <img src="https://static.pepy.tech/badge/sweepai/month" />
</a>
<a href="https://github.com/sweepai/sweep">
    <img src="https://img.shields.io/github/stars/sweepai/sweep" />
</a>
<a href="https://twitter.com/sweep__ai">
    <img src="https://img.shields.io/twitter/url?url=https%3A%2F%2Ftwitter.com%2Fsweep__ai" />
</a>
</p>

<b>Sweep</b> is an AI junior developer that transforms bug reports & feature requests into code changes.

Describe bugs, small features, and refactors like you would to a junior developer, and Sweep:
1. 🔍 reads your codebase
2. 📝 plans the changes
3. ⚡**writes a pull request with code**⚡

See highlights at https://docs.sweep.dev/examples.

[Demo](https://github.com/sweepai/sweep/assets/44910023/365ec29f-7317-40a7-9b5e-0af02f2b0e47)

## 🌠 Sweep
* 🔧 Turns issues directly into pull requests (without an IDE)
* 👀 Addresses developer replies & comments on its PRs
* 🕵️‍♂️ Uses embedding-based code search, with popularity reranking for repository-level code understanding ([🔍 Rebuilding our Search Engine in a Day](https://docs.sweep.dev/how-we-rebuilt-our-code-search-engine-in-a-day))
* 🎊 New: Fixes PRs based on Github Actions feedback
* 🎊 New: Sweep Chat, a local interface for Sweep (see below)

## 🚀 Getting Started

### 🍲 Recipes
#### To get the best performance from Sweep, we recommend the following approach to writing github issues/chats. 
For harder problems, try to provide the same information a human would need. For simpler problems, providing a single line and a file name should suffice.

A good issue might include:

| Where to look <br> **[file name or function name]**| What to do <br> **[change the logic to do this]** | Additional Context (optional) <br> **[there's a bug/we need this feature/there's this dependency]** |
|-----------|------------|----------------------|
|In `sweepai/app/ui.py`|use an os-agnostic temp directory|N/A|
|In `on_comment.py`|we should not fire an event|because it's possible that the comment is on a closed PR|
|In the config loader in `packages/server/src/config.ts`|add a third option called "env" to load the config settings from environment variables| At present, there are two options:  1. ... and 2. ...|

If you want Sweep to use a file, try to mention the full path. Similarly, to have Sweep use a function, try to mention the class method or what it does. Also see [✨ Tips and tricks for Sweep](https://docs.sweep.dev/tricks).

#### Limitations:
Sweep is unlikely to complete complex issues on the first try, similar to the average junior developer. Here are Sweep's limitations(for now):
- Try to change less than 200 lines of code
- Try to modify less than 3 files
- Do not include files with more than 1500 lines of code

### ✨ Sweep Github App
Setting up Sweep is as simple as adding the GitHub bot to a repo, then creating an issue for the bot to address.
We support all languages GPT4 supports, including Python, Typescript, Rust, Go, Java, C# and C++.

1. Add the [Sweep GitHub app](https://github.com/apps/sweep-ai) to desired repos
2. Create new issue in repo, like "Sweep: In sweepai/app/ui.py use an os-agnostic temp directory"

### 🖥️ Sweep Chat
Sweep Chat allows you to interact with Sweep and GitHub locally. Collaborate on the plan with Sweep, then have it create the pull request for you. 

**Prerequisites:** Install [Sweep GitHub app](https://github.com/apps/sweep-ai) to your repository

1. Run `pip3 install sweepai && sweep`. Note that you need **python 3.10+.**
    - Alternatively run `pip3 install --force-reinstall sweepai && sweep` if the previous command fails.
    - This runs GitHub authentication in your browser.

2. Copy the 🔵 blue 8-digit code from your terminal into the page. You should only need to do the authentication once.  
    - Wait a few seconds and Sweep Chat will start. 

3. Choose a repository from the dropdown at the top (the Github app must be installed to this repository).

    - ⚡ Start chatting with Sweep Chat! ⚡

<img src="https://github.com/sweepai/sweep/blob/856ff66c2dbeaf39afbf6d8c49a620dfa70271fb/.assets/gradio-screenshot.png">

Tips:
* 🔍 Relevant searched files will show up on the right. 
* 🔘 Sweep Chat creates PRs when the "Create PR" button is clicked. 
* 💡 You can force dark mode by going to http://127.0.0.1:7861/?__theme=dark.

#### From Source
If you want the nightly build and or if the latest build has issues.

1. `git clone https://github.com/sweepai/sweep && poetry install`
2. `python sweepai/app/cli.py`. Note that you need **python 3.10+**.

## 💰 Pricing
* We charge $120/month for 60 GPT4 tickets per month.
* For unpaid users, we offer 3 free GPT4 tickets per month.
* We also offer unlimited GPT3.5 tickets.
## 🤝 Contributing

Contributions are welcome and greatly appreciated! For detailed guidelines on how to contribute, please see the [CONTRIBUTING.md](CONTRIBUTING.md) file.
For more detailed docs, see [🚀 Quickstart](https://docs.sweep.dev/).

## 📘 Story

We were frustrated by small tickets, like simple bug fixes, annoying refactors, and small features. Each task required us to open our IDE to fix simple bugs. So we decided to leverage the capabilities of ChatGPT to address this directly in GitHub.

Unlike existing AI solutions, this can solve entire tickets and can be parallelized + asynchronous: developers can spin up 10 tickets and Sweep will address them all at once.

## 📚 The Stack
- GPT-4 32k 0613 (default)
- ActiveLoop DeepLake for Vector DB with MiniLM L12 as our embeddings model
- Modal Labs for infra + deployment
- Gradio for Sweep Chat

## 🗺️ Roadmap
See [🗺️ Roadmap](https://docs.sweep.dev/roadmap)

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=sweepai/sweep&type=Date)](https://star-history.com/#sweepai/sweep&Date)

Consider starring us if you're using Sweep so more people hear about us!
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
