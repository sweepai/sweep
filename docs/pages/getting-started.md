# Welcome - Sweep installed successfully! 🎉

*You should be redirected here after installing Sweep. If you haven't installed Sweep, install [here](https://github.com/apps/sweep-ai).*

⚠️ Sweep works best with real repositories and real issues; empty or test repositories will break Sweep. *If you don't have a good repo at hand, check out our [tutorial on running Sweep on Docusaurus](https://docs.sweep.dev/usage/tutorial).*

If you prefer video, [check out our demo (2 min)](https://www.youtube.com/watch?v=fr5V5EWVcyM&lc=UgxM_ZzFiFYfjo1ADU54AaABAg)

## Create an issue on your own repository
The issue title should start with `Sweep: `. For issues and PRs, call Sweep using the Sweep label or by prefixing your text with `Sweep: `. For existing GitHub issues, add the `Sweep` label to the issue.

<table>
  <tr>
    <td style="border: 2px solid black;">
      <img src="https://github.com/sweepai/sweep/assets/44910023/68b345eb-0ae5-455e-a1a3-c388b1f032f6" alt="Image description">
    </td>
  </tr>
</table>

To get Sweep to work off an existing branch, add to the end of the issue description:

```
Branch: feat/name-of-branch
```

Note: The initial startup time typically takes around 3-5 minutes depending on your codebase, since we will have to index your codebase.

## Fix Sweep's PRs

Sweep will mess up sometimes. Comment on it's PR. (ex: "use PyTorch instead of Tensorflow".)
- You can also comment in the issue and code. See [Commenting](https://docs.sweep.dev/usage/advanced#giving-sweep-feedback).
- To have Sweep automatically improve it's PRs, use Github Actions. See [GHA Tech Blog](https://docs.sweep.dev/blogs/giving-dev-tools)
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
* Describe the changes or fixes you want, optionally mentioning implementation details.
* Provide any additional context that might be helpful, e.g. see "src/App.test.tsx" for an example of a good unit test.
* For more guidance, visit [Advanced](https://docs.sweep.dev/usage/advanced), or watch the following video.

[![Video](http://img.youtube.com/vi/Qn9vB71R4UM/0.jpg)](http://www.youtube.com/watch?v=Qn9vB71R4UM "Advanced Sweep Tricks and Feedback Tips")

For configuring Sweep for your repo, see [Config](https://docs.sweep.dev/usage/config), especially for setting up Sweep Rules.

## Limitations of Sweep (for now) ⚠️

* 🗃️ **Gigantic repos**: >5000 files. We have default extensions and directories to exclude but sometimes this doesn't catch them all. You may need to block some directories (see [`blocked_dirs`](https://docs.sweep.dev/usage/config#blocked_dirs))
> If Sweep is stuck at 0% for over 30 min and your repo has a few thousand files, let us know.


* 🏗️ **Large-scale refactors**: >5 files or >300 lines of code changes (we're working on this!)
> We can't do this - "Refactor entire codebase from Tensorflow to PyTorch"


* 🖼️ **Editing images** and other non-text assets
> We can't do this - "Use the logo to create favicons for our landing page"


* ⤵️ **Accessing external APIs**, including fetching API tokens
> We can't do this - "Set up sign-in using Ethereum"

## Pricing
We offer unlimited GPT3.5 tickets to every user. Every user also starts with 5 GPT4 issues a month, and you'll be able to use 2 GPT-4 issues a day.

For hobbyists who want more tickets, check out [Sweep Plus](https://buy.stripe.com/7sI5np26l1H24QU7sA) now at $120/month for 30 tickets.

For professionals who want even more tickets and priority support/feature requests, check out [Sweep Pro](https://buy.stripe.com/00g5npeT71H2gzCfZ8) now at $480/month for unlimited tickets.

---

# Bug Reports

If Sweep fails to solve your issue that is within the scope of Sweep (see Limitations) and you submit a high-quality bug report at our [Discourse](https://community.sweep.dev/), we will reset your ticket count, giving your GPT-4 tickets back. This is only for GPT4 PRs.
