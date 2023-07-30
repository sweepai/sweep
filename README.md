<p align="center">
    <img src="https://github.com/sweepai/sweep/assets/26889185/39d500fc-9276-402c-9ec7-3e61f57ad233">
</p>
<p align="center">
    <i>Bug Reports & Feature Requests ⟶&nbsp; Code Changes</i>
</p>

<p align="center">
<a href="https://sweep.dev">
    <img alt="Install" src="https://img.shields.io/badge/Install-sweep.dev-blue?link=https%3A%2F%2Fsweep.dev">
</a>
<a href="https://docs.sweep.dev/">
    <img alt="Docs" src="https://img.shields.io/badge/Docs-docs.sweep.dev-blue?link=https%3A%2F%2Fdocs.sweep.dev">
</a> 
<a href="https://discord.gg/sweep-ai">
    <img src="https://dcbadge.vercel.app/api/server/sweep-ai?style=flat" />
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

### Features 🌠
* 🌠 Turns issues directly into pull requests (without an IDE)
* 👀 Addresses developer replies & comments on its PRs
* 🔎 Uses embedding-based code search
* 🔧 Fixes PRs based on GitHub Actions feedback
* 🎈 Large File Support using File Streaming

[Demo](https://github.com/sweepai/sweep/assets/44910023/365ec29f-7317-40a7-9b5e-0af02f2b0e47)

---

## Getting Started 🚀

Install Sweep by adding the [**Sweep GitHub app**](https://github.com/apps/sweep-ai) to your desired repositories.

* For more details, visit our [✨ Installation](docs/installation.md) page.

* Note: Sweep only considers issues with the "Sweep:" title on creation and not on update. If you want Sweep to pick up an issue after it has been created, you can add the "Sweep" label to the issue.

* We support all languages GPT-4 supports, including Python, JS/TS, Rust, Go, Java, C# and C++.

## Limitations of Sweep ⚠️

* 🏗️ **Large-scale refactors**: >3 files or >150 lines of code changes (we're working on this!)
    * e.g. Refactor entire codebase from Tensorflow to PyTorch

* ⏲️ **Using the latest APIs** that have changed past 2022
    * e.g. Set up a vector store using LlamaIndex Typescript    
    * 🎩 If you provide the relevant docs however, then Sweep can do this

* 🖼️ **Editing images** and other non-text assets
    * e.g. Use the logo to create favicons for our landing page

* ⤵️ **Accessing external APIs**, including fetching API tokens
    * e.g. Set up sign-in using Ethereum

---

## Story 📘

We were frustrated by small tickets, like simple bug fixes, annoying refactors, and small features. Each task required us to open our IDE to fix simple bugs. So we decided to leverage the capabilities of ChatGPT to address this directly in GitHub.

Unlike existing AI solutions, this can solve entire tickets and can be parallelized + asynchronous: developers can spin up 10 tickets and Sweep will address them all at once.

## The Stack 📚
- GPT-4 32k 0613 (default)
- ActiveLoop DeepLake for Vector DB with MiniLM L12 as our embeddings model
- Modal Labs for infra + deployment

## Highlights 🌟
Examine pull requests created by Sweep [here](https://docs.sweep.dev/examples).

## Pricing 💎
* We charge $240/month for 120 GPT-4 tickets per month.
* For unpaid users, we offer 5 free GPT-4 tickets per month.
* We also offer unlimited GPT-3.5 tickets.

## Roadmap 🗺
See [🗺️ Roadmap](https://docs.sweep.dev/roadmap)

---

## Star History ⭐

[![Star History Chart](https://api.star-history.com/svg?repos=sweepai/sweep&type=Date)](https://star-history.com/#sweepai/sweep&Date)

Consider starring us if you're using Sweep so more people hear about us!

## Contributing 🤝
Contributions are welcome and greatly appreciated! For detailed guidelines on how to contribute, please see the [CONTRIBUTING.md](CONTRIBUTING.md) file.
* [Sweep Docs](https://docs.sweep.dev/).


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
