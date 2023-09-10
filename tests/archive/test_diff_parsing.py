from sweepai.utils.diff import generate_new_file_from_patch

old_file = r"""
## August 5, 2023

- William: @[Alerts: Minor Updates] ⏩ We just pushed fixes that should speed up Sweep's first step by a lot, especially for large repos (could have taken 5 minutes+, should now be sub 1 minute). Sweep was slow because of a hotfix we pushed due to our infra provider having issues. Now that Sweep is working reliably, we're working on getting the speed back 🚤
- William: Just pushed an improvement that should really improve latency. We were previously updating the cache for inactive users, which slows everything down. We now only do this for active and Sweep Pro users. :sweeping:
- Kevin: @[Alerts: Minor Updates] 🎉 More exciting features from this evening:
  🔴 Sweep live updates when coding to indicate which files are done by Sweep (see screenshot).
  🔄 Review comments are now moved to the issues thread to not clutter the PR, and the PR is only generated when the self-review is done. Further, prefixing with "sweep (slow):" gives you up to 3 self-reviews, though it can take up to 10 minutes to run.
- William: Hey everyone, we have some issues with modifying files (you'll see this error at 60%). Apologies, I'm on this now.
- William: @[Alerts: Minor Updates] ⏩ We just pushed fixes that should speed up Sweep's first step by a lot, especially for large repos (could have taken 5 minutes+, should now be sub 1 minute). Sweep was slow because of a hotfix we pushed due to our infra provider having issues. Now that Sweep is working reliably, we're working on getting the speed back 🚤
- Kevin: The erroneous GitHub Actions logs should be mostly fixed now. Let me know if you still get a GitHub Action with the wrong logs.
- @[Alerts: Minor Updates] 🎊 Some new features from this evening:
  Sweep's errors rate during execution should be greatly reduced: we improved how Sweep determines what to keep in context and what to delete
  Sweep handles long discussions better: Sweep now cleans long conversations and rewrites issue content internally
- Kevin: ⚡ We just released further optimization for search! We noticed that the queue times recently have been very long so for small updates on repos we use CPU to re-embed the new files, which is faster than the queue times!
"""

code_replaces = r"""
```
<<<< ORIGINAL
## August 5, 2023

- William: @[Alerts: Minor Updates] ⏩ We just pushed fixes that should speed up Sweep's first step by a lot, especially for large repos (could have taken 5 minutes+, should now be sub 1 minute). Sweep was slow because of a hotfix we pushed due to our infra provider having issues. Now that Sweep is working reliably, we're working on getting the speed back 🚤
====
## August 5, 2023

- William: ⏩ We just pushed fixes that should speed up Sweep's first step by a lot, especially for large repos (could have taken 5 minutes+, should now be sub 1 minute). Sweep was slow because of a hotfix we pushed due to our infra provider having issues. Now that Sweep is working reliably, we're working on getting the speed back 🚤
>>>> UPDATED
```
"""

if __name__ == "__main__":
    print(generate_new_file_from_patch(code_replaces, old_file)[0])
    # generate_new_file_from_patch(code_replaces, old_file)[0]
  