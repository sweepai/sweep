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
* 🎊 New: Fixes PRs based on GitHub Actions feedback
* 🎊 New: Sweep Chat, a local interface for Sweep (see below)
* 🎊 New: Enhanced file handling with streaming logic in modify_file, allowing for larger files to be processed. This new logic streams code in chunks, which allows Sweep to handle files of any size. This removes the previous limitation on file size, making Sweep more versatile and capable of handling larger projects.

## 🚀 Getting Started

### ✨ Sweep Github App
Setting up Sweep is as simple as adding the GitHub bot to a repo, then creating an issue for the bot to address. Here are the steps to get started:

1. Add the [Sweep GitHub app](https://github.com/apps/sweep-ai) to your desired repos
2. Read about [recipes](docs/Recipes.md) for best use cases.
2. Create a new issue in your repo. The issue should describe the problem or feature you want Sweep to address. For example, you could write "Sweep: In sweepai/app/ui.py use an os-agnostic temp directory"
3. Respond with a message like "Sweep: use a different package instead" to have Sweep retry the issue or pull request. You can also comment on the code for minor changes! Remember to put the "Sweep:" prefix.
   - 💡 Hint: commenting "revert" reverts all edits in a file.

We support all languages GPT4 supports, including Python, Typescript, Rust, Go, Java, C# and C++.

### 🗨️ Sweep Chat
Sweep Chat allows you to interact with Sweep and GitHub locally. You can collaborate on the plan with Sweep, and then have it create the pull request for you. Here's how to use Sweep Chat:

**Prerequisites:** Install [Sweep GitHub app](https://github.com/apps/sweep-ai) to your repository

1. Run `pip3 install sweepai && sweep`. Note that you need **python 3.10+.**
    - Alternatively run `pip3 install --force-reinstall sweepai && sweep` if the previous command fails.
    - This runs GitHub authentication in your browser.

2. Copy the 🔵 blue 8-digit code from your terminal into the page. You should only need to do the authentication once.  
    - Wait a few seconds and Sweep Chat will start. 

3. Choose a repository from the dropdown at the top (the Github app must be installed to this repository).
    - ⚡ Start chatting with Sweep Chat! ⚡


![Screenshot_20230711_015033](https://github.com/sweepai/sweep/assets/26889185/ed9f05d8-ef86-4f2a-9bca-acdfa24990ac)

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
