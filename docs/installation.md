# Welcome to Sweep - GitHub App installed successfully! 🎉

⚠️ Be sure to follow these instructions in your own repository.

If you prefer video, [check out our demo (2 min)](https://www.youtube.com/watch?v=fr5V5EWVcyM&lc=UgxM_ZzFiFYfjo1ADU54AaABAg)

## Create an issue on your own repository
The issue title should start with `Sweep: ` For issues and PRs, call Sweep using the Sweep label or by prefixing your text with `Sweep: `
- **Sweep works best with real repositories and real issues.**


<table>
  <tr>
    <td style="border: 2px solid black;">
      <img src="https://github.com/sweepai/sweep/assets/44910023/68b345eb-0ae5-455e-a1a3-c388b1f032f6" alt="Image description">
    </td>
  </tr>
</table>

Note: The initial startup time typically takes around 3-5 minutes depending on your codebase.

## Fix Sweep's PRs

Sweep will mess up sometimes. Comment on it's PR. (ex: "use PyTorch instead of Tensorflow".)
- You can also comment in the issue and code. See [Commenting](https://docs.sweep.dev/commenting).
- To have Sweep automatically improve it's PRs, use Github Actions. [GHA Tech Blog](https://docs.sweep.dev/blogs/giving-dev-tools)
- To disable Sweep on a PR/issue, remove the Sweep label.


<table>
  <tr>
    <td style="border: 2px solid black;">
      <img src="https://github.com/sweepai/sweep/assets/44910023/9323aa0c-0f32-4da1-89bc-418e44372d8b" alt="Image description">
    </td>
  </tr>
</table>


## Sweep Prompting Tricks 📝

* Mention filenames or function names.
* Describe the changes or fixes you want.
* Provide any additional context that might be helpful.
* For more guidance, visit [Sweep Recipes](https://docs.sweep.dev/recipes).

## Limitations of Sweep (for now) ⚠️

* 🏗️ **Large-scale refactors**: >3 files or >150 lines of code changes (we're working on this!)
    * We can't do this - "Refactor entire codebase from Tensorflow to PyTorch"

* ⏲️ **Using the latest APIs** that have changed past 2022
    * We can't do this - "Set up a vector store using LlamaIndex Typescript"
    * 🎩 However if you provide the relevant docs as links/text, then Sweep will read them and make the changes.

* 🖼️ **Editing images** and other non-text assets
    * We can't do this - "Use the logo to create favicons for our landing page"

* ⤵️ **Accessing external APIs**, including fetching API tokens
    * We can't do this - "Set up sign-in using Ethereum"

## Pricing
We offer unlimited GPT3.5 tickets to every user. Every user also starts with 5 GPT4 issues a month, and you'll be able to use 2 GPT4 issues a day.

For professionals who want more tickets and priority support/feature requests, check out [Sweep Pro](https://buy.stripe.com/6oE5npbGVbhC97afZ4) now at $480/month. In addition, we're also offering 15 PRs for $60 as a one-time purchase for anyone interested in eventually purchasing Sweep Pro. You can avail this offer [here](https://buy.stripe.com/7sI4jlaCR3PaabebIP).

---

### Documentation 📚

[Check out our docs](https://docs.sweep.dev/).

### Contact Us 👥
- [Discord](https://discord.com/invite/sweep-ai)
- team@sweep.dev
- [Star us on GitHub! ⭐](https://github.com/sweepai/sweep)


Note - you need to have Sweep installed and [Issues enabled in Repo](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/disabling-issues)

# Bug Reports

If Sweep fails to solve your issue that is within the scope of Sweep (see Limitations) and you submit a high-quality bug report at our [Discord](https://discord.gg/sweep), we will reset your ticket count, giving your GPT-4 tickets back. This is only for GPT4 PRs.
