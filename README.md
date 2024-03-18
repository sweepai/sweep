<p align="center">
    <img src="https://github.com/sweepai/sweep/assets/26889185/39d500fc-9276-402c-9ec7-3e61f57ad233">
</p>
<p align="center">
    <i>Github Issues ⟶&nbsp; Pull Requests! </i>
</p>
<p align="center">
    <a href="https://github.com/apps/sweep-ai">
        <img alt="Install Sweep Github App" src="https://img.shields.io/badge/Install Sweep-GitHub App-purple?link=https://github.com/apps/sweep-ai">
    </a>
    <a href="https://discord.gg/sweep">
        <img src="https://dcbadge.vercel.app/api/server/sweep?style=flat" />
    </a>
    <a href="https://hub.docker.com/r/sweepai/sweep">
        <img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/sweepai/sweep" />
    </a>
    <a href="https://docs.sweep.dev/">
        <img alt="Docs" src="https://img.shields.io/badge/Docs-docs.sweep.dev-red?link=https%3A%2F%2Fdocs.sweep.dev">
    </a>
    <a href="https://github.com/sweepai/sweep">
        <img src="https://img.shields.io/github/commit-activity/m/sweepai/sweep" />
    </a>
    <a href="https://pypi.org/project/sweepai">
        <img src="https://badge.fury.io/py/sweepai.svg" alt="PyPI version" height="18">
    </a>
    <a href="https://hub.docker.com/r/sweepai/sweep">
        <img alt="Self Host Sweep Docker Image" src="https://img.shields.io/badge/Host Sweep-Docker Image-2496ED?link=https://hub.docker.com/r/sweepai/sweep">
    </a>
    <a href="https://github.com/sweepai/sweep/actions/workflows/unittest.yml">
        <img src="https://github.com/sweepai/sweep/actions/workflows/unittest.yml/badge.svg" alt="Python Unit Tests">
    </a>
</p>

---

<b>Sweep</b> is an AI junior developer that turns bugs and feature requests into code changes. Sweep automatically handles devex improvements like adding typehints/improving test coverage. :robot:

[Install Sweep](https://github.com/apps/sweep-ai) and open a Github Issue like: `Sweep: Add typehints to src/utils/github_utils.py` and Sweep will:
1. Search through your codebase to find the dependencies of github_utils.py
2. Modify the code to add typehints
3. **Run and debug your code to write a Pull Request** ⚡

### Features
* Turns issues directly into pull requests (without an IDE)
* Addresses developer replies & comments on its PRs
* Understands your codebase using the dependency graph, text, and vector search.
* Runs your unit tests and autoformatters to validate generated code.
* Stack small fixes into your PR by applying [Sweep Rules](https://docs.sweep.dev/usage/config#tips-for-writing-rules)

[![Sweep Youtube Tutorial](docs/public/assets/youtube_thumbnail.png)](https://www.youtube.com/watch?v=GVEkDZmWw8E)


> [!NOTE]
> ### What makes Sweep Different
> We've been addressing code modification using LLMs for a while. We found and are fixing a lot of issues.
>  - **Modifying Code** - LLMs like GPT4 don't have a great way to automatically modify code. We heavily experiment on different ways to modify code so you don't have to. We've spent a really long time working on this - check out https://docs.sweep.dev/blogs/gpt-4-modification!
> - **Planning Code Changes** - Retrieval-Augmented-Generation isn't enough. We wrote a code chunker that's used fairly heavily, and we're constantly improving this: https://docs.sweep.dev/blogs/chunking-improvements
> -  Sweep runs your **Github Actions**, catching bugs and making sure each line of new code has been properly validated!
> -  **Sweep** uses it's sandbox to format your code, and uses [Rules](https://docs.sweep.dev/usage/config#tips-for-writing-rules) to perform other changes like adding typehints, or any other small chores!


## Getting Started

### GitHub App
Install Sweep by adding the [**Sweep GitHub App**](https://github.com/apps/sweep-ai) to your desired repositories.

* For more details, visit our [installation page](https://docs.sweep.dev/getting-started).

* Note: Sweep only considers issues with the "Sweep:" title on creation and not on update. If you want Sweep to pick up an existing issue, you can add the "Sweep" label to the issue.

* We focus on Python but support all languages GPT-4 can write. This includes JS/TS, Rust, Go, Java, C# and C++.

### Self-Hosting

You can self-host Sweep with our Docker image (`https://hub.docker.com/r/sweepai/sweep`). Please check out our deployment instructions here! https://docs.sweep.dev/deployment

## Development

### Starting the Webhook
1. Clone the repo with `git clone https://github.com/sweepai/sweep`.
2. Create `.env` according to https://docs.sweep.dev/deployment.
3. Run `docker compose up --build`. This will take a few moments to start.

To build our Docker images, run `docker compose build`.

---

## Story

We used to work in large, messy repositories, and we noticed how complex the code could get without regular refactors and unit tests. We realized that AI could handle these chores for us, so we built Sweep!

Unlike existing AI solutions, Sweep can solve entire tickets and can be parallelized + asynchronous: developers can spin up 10 tickets and Sweep will address them all at once.

## Highlights
[Examine pull requests created by Sweep!](https://docs.sweep.dev/about/examples)

## Pricing
Every user receives unlimited GPT-3.5 tickets and 5 GPT-4 tickets per month. For professionals who want to try unlimited GPT-4 tickets and priority support, you can get a one week free trial of [Sweep Pro](https://buy.stripe.com/00g5npeT71H2gzCfZ8).

For more GPT-4 tickets visit <a href='https://buy.stripe.com/00g3fh7qF85q0AE14d'>our payment portal</a>!

You can [self-host](https://docs.sweep.dev/deployment) Sweep's docker image on any machine (AWS, Azure, your laptop) for free. You can get enterprise support by [contacting us](https://form.typeform.com/to/wliuvyWE).

---

> [!WARNING]
> ### Limitations of Sweep
> * **Gigantic repos**: >5000 files. We have default extensions and directories to exclude but sometimes this doesn't catch them all. You may need to block some directories (see [`blocked_dirs`](https://docs.sweep.dev/usage/config#blocked_dirs))
    * If Sweep is stuck at 0% for over 30 min and your repo has a few thousand files, let us know.
> * **Large-scale refactors**: >3 files or >150 lines of code changes
    * e.g. Refactor the entire codebase from TensorFlow to PyTorch
    * Sweep works best when pointed to a file, and we're continously improving Sweep's automation!
> * **Editing images** and other non-text assets
    * e.g. Use the logo to create favicons for our landing page
---

## Contributing

Contributions are welcome and greatly appreciated! To get set up, see [Development](https://github.com/sweepai/sweep#development). For detailed guidelines on how to contribute, please see the [CONTRIBUTING.md](CONTRIBUTING.md) file.


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
