<p align="center">
    <img src="https://github.com/sweepai/sweep/assets/26889185/39d500fc-9276-402c-9ec7-3e61f57ad233">
</p>
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

## 🌠 Features
* 🔧 Turns issues directly into pull requests (without an IDE)
* 👀 Addresses developer replies & comments on its PRs
* 🕵️‍♂️ Uses embedding-based code search, with popularity reranking for repository-level code understanding ([🔍 Rebuilding our Search Engine in a Day](https://docs.sweep.dev/blogs/building-code-search))
* 👨‍⚕️ Fixes PRs based on GitHub Actions feedback
* 🎊 New: Enhanced file handling with streaming logic in modify_file, allowing for larger files to be processed.
* 🎊 New: Handles comments and reviews in a batch (leave 5+ comments at a time)

## 🚀 Getting Started

### 🍲 Recipes
#### To get the best performance from Sweep, we recommend the following approach to writing github issues. 
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
- Try to change less than 300 lines of code
- Try to modify less than 5 files

### ✨ Sweep Github App
Setting up Sweep is as simple as adding the GitHub bot to a repo, then creating an issue for the bot to address. Here are the steps to get started:

1. Add the [Sweep GitHub app](https://github.com/apps/sweep-ai) to your desired repos
2. Create a new issue in your repo. The issue should describe the problem or feature you want Sweep to address. For example, you could write "Sweep: In sweepai/app/ui.py use an os-agnostic temp directory"
3. Respond with a message like "Sweep: use a different package instead" to have Sweep retry the issue or pull request. You can also comment on the code for minor changes! Remember to put the "Sweep:" prefix.
   - 💡 Hint: commenting "revert" reverts all edits in a file.
4. For more information, visit [https://sweep.dev](https://sweep.dev).

We support all languages GPT4 supports, including Python, Typescript, Rust, Go, Java, C# and C++.

## 💰 Pricing
* We charge $240/month for 120 GPT4 tickets per month.
* For unpaid users, we offer 5 free GPT4 tickets per month.
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
