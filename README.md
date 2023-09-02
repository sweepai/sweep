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
<a href="https://discord.gg/sweep">
    <img src="https://dcbadge.vercel.app/api/server/sweep?style=flat" />
</a>
<a href="https://github.com/sweepai/sweep">
    <img src="https://img.shields.io/github/stars/sweepai/sweep" />
</a>
<a href="https://twitter.com/sweep__ai">
    <img src="https://img.shields.io/twitter/url?url=https%3A%2F%2Ftwitter.com%2Fsweep__ai" />
</a>
</p>

<p align="center">
    <a href="https://cloud.digitalocean.com/apps/new?repo=https://github.com/sweepai/sweep/tree/main">
        <img src="https://www.deploytodo.com/do-btn-white-ghost.svg" alt="Deploy to DO">
    </a>
<p>

*🎉 We recently changed our license to the Elastic License V2 to allow Sweep for commercial usage.*

---

<b>Sweep</b> is an AI junior developer that transforms bug reports & feature requests into code changes.

Describe bugs, small features, and refactors like you would to a junior developer, and Sweep:
1. Reads your codebase
2. Plans the changes
3. **Writes a pull request with code** ⚡

### Features

* Turns issues directly into pull requests (without an IDE)
* Addresses developer replies & comments on its PRs
* Uses embedding-based code & online document search
* Validates its changes with GitHub Actions and self-review

### Why Choose Sweep?

We're not a toy project or a proof-of-concept. We're a **production devtool** used by startups including ourselves to ship features everyday, with example features [here](https://docs.sweep.dev/about/examples).
Unlike Copilot, which only provides IDE-based autocompletion, Sweep handles the **entire flow end-to-end**. Unlike ChatGPT, Sweep is able to automatically understand and search through your code base, removing the need to tediously copy-and-paste files.

<details>
    <summary>
        Sweep vs. GPT-Engineer, Smol Developer and AutoGPT
    </summary>
    Sweep is built to improve on an existing codebase, which is a more frequent and higher need, than generating boilerplate, which is mostly a solved problem since you can just fork existing boilerplates.
</details>

<details>
    <summary>
        Sweep vs. Cody and Bloop
    </summary>
    We do more than just chat-with-your-code by actually writing code changes.
</details>

[Demo](https://github.com/sweepai/sweep/assets/44910023/365ec29f-7317-40a7-9b5e-0af02f2b0e47)

---

## Getting Started

Install Sweep by adding the [**Sweep GitHub App**](https://github.com/apps/sweep-ai) to your desired repositories.

* For more details, visit our [Installation](docs/installation.md) page.

* Note: Sweep only considers issues with the "Sweep:" title on creation and not on update. If you want Sweep to pick up an issue after it has been created, you can add the "Sweep" label to the issue.

* We support all languages GPT-4 supports, including Python, JS/TS, Rust, Go, Java, C# and C++.

## Self-hosting

You can self-host Sweep with the Docker image (`https://hub.docker.com/r/sweepai/sweep`). The setup instructions are at [Deployment](https://docs.sweep.dev/deployment).

## Limitations of Sweep

* **Large-scale refactors**: >3 files or >150 lines of code changes (we're working on this!)
    * e.g. Refactor the entire codebase from TensorFlow to PyTorch

* **Editing images** and other non-text assets
    * e.g. Use the logo to create favicons for our landing page

* **Performing actions involving a dashboard**, including fetching API tokens
    * e.g. Set up sign-in using Ethereum

---

## Story

We were frustrated by small tickets, like simple bug fixes, annoying refactors, and small features. Each task required us to open our IDE to fix simple bugs. So we decided to leverage the capabilities of ChatGPT to address this directly in GitHub.

Unlike existing AI solutions, this can solve entire tickets and can be parallelized + asynchronous: developers can spin up 10 tickets and Sweep will address them all at once.

## The Stack
- **GPT-4 32k** & GPT-3.5 16k
- GTE-base embedding model
- ActiveLoop DeepLake Vector DB
- Modal Labs for infra + deployment

## Highlights
Examine pull requests created by Sweep [here](https://docs.sweep.dev/about/examples).

## Pricing
Every user receives unlimited GPT-3.5 tickets and 5 GPT-4 tickets per month. To prevent abuse, users can use 2 GPT-4 tickets a day.

For professionals who want more tickets and priority support/feature requests, check out [Sweep Pro](https://buy.stripe.com/6oE5npbGVbhC97afZ4) now at $480/month. In addition, we're also offering 15 PRs for $60 as a one-time purchase for anyone interested in eventually purchasing Sweep Pro. You can purchase this [here](https://buy.stripe.com/7sI4jlaCR3PaabebIP).

## Roadmap
We plan on rapidly improving Sweep. To see what we're working on, check out our [Roadmap](https://docs.sweep.dev/roadmap).

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=sweepai/sweep&type=Date)](https://star-history.com/#sweepai/sweep&Date)

Consider starring us if you're using Sweep so more people hear about us!

## Contributing
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
