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
<br>
<a href="https://www.producthunt.com/posts/sweep-5?utm_source=badge-featured&utm_medium=badge&utm_souce=badge-sweep&#0045;5" target="_blank"><img src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=404410&theme=neutral" alt="Sweep - Sweep&#0032;is&#0032;an&#0032;AI&#0045;powered&#0032;junior&#0032;dev&#0032;on&#0032;your&#0032;team&#0046; | Product Hunt" style="width: 175px; height: 36px;" width="175" height="36" /></a>
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
* 🕵️‍♂️ Uses embedding-based code search, with popularity reranking for repository-level code understanding ([🔍 Rebuilding our Search Engine in a Day](https://docs.sweep.dev/blogs/building-code-search))
* 🎊 New: Fixes PRs based on Github Actions feedback
* 🎊 New: Sweep Chat, a local interface for Sweep (see below)

## 🚀 Getting Started
def main():
    print("hello world")
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
Setting up Sweep is as simple as adding the GitHub bot to a repo, then creating an issue for the bot to address. Here are the steps to get started:

1. Add the [Sweep GitHub app](https://github.com/apps/sweep-ai) to your desired repos
print("debug statement")
2. Create a new issue in your repo. The issue should describe the problem or feature you want Sweep to address. For example, you could write "Sweep: In sweepai/app/ui.py use an os-agnostic temp directory"
3. Respond with a message like "Sweep: use a different package instead" to have Sweep retry the issue or pull request. You can also comment on the code for minor changes!

We support all languages GPT4 supports, including Python, Typescript, Rust, Go, Java, C# and C++.

### 🖥️ Sweep Chat
Sweep Chat allows you to interact with Sweep and GitHub locally. You can collaborate on the plan with Sweep, and then have it create the pull request for you. Here's how to use Sweep Chat:

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
