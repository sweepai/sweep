### 🍲 Recipes
#### To get the best performance from Sweep, we recommend the following approach to writing github issues/chats.
For harder problems, try to provide the same information a human would need. For simpler problems, providing a single line and a file name should suffice.

A good issue might include:

| Where to look <br> **[file name or function name]**| What to do <br> **[change the logic to do this]** | Additional Context (optional) <br> **[there's a bug/we need this feature/there's this dependency]** |
|-----------|------------|----------------------|
|In `sweepai/app/ui.py`|use an os-agnostic temp directory|N/A|
|In `on_comment.py`|we should not fire an event|because it's possible that the comment is on a closed PR|
|In the config loader in `packages/server/src/config.ts`|add a third option called "env" to load the config settings from environment variables| At present, there are two options:  1. ... and 2. ...|

If you want Sweep to use a file, try to mention the full path. Similarly, to have Sweep use a function, try to mention the class method or what it does. Also see [✨ Tips and tricks for Sweep](https://docs.sweep.dev/usage/advanced).

#### Limitations:
Sweep is unlikely to complete complex issues on the first try, similar to the average junior developer. Here are Sweep's limitations(for now):
- Try to change less than 300 lines of code
- Try to modify less than 3 files
