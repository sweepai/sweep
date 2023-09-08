# Changelog

## August 8, 2023
- [Alerts: Minor Updates] We just launched external documentation search! 📚 For example, if you want Sweep to use the OpenAI docs, you can mention “openai” in your issue and Sweep will search over the OpenAI docs for you. 👀

Right now we’ve manually indexed the documentation for frameworks like Langchain, ReactJS, and Docusaurus here: https://github.com/sweepai/sweep/blob/main/sweepai/core/documentation.py#L37-L47. You can mention those now to start using them!

We’ll also allow you to add your own documentation soon, so look out for that tomorrow 😀

The page contains code snippets from the file `sweepai/core/documentation.py`. The code includes imports from various modules and libraries such as `asyncio`, `re`, `deeplake.core.vectorstore.deeplake_vectorstore`, `loguru`, `tqdm`, `sweepai.core.lexical_search`, `sweepai.core.robots`, `sweepai.core.webscrape`, `sweepai.pre_indexed_docs`, and `sweepai.config.server`. 

The code defines a class called `ModalEmbeddingFunction` with methods `__init__` and `__call__`. It also defines a class called `CPUEmbedding` with methods `__init__` and `compute`. Additionally, there is a function called `chunk_string`.

The code uses a constant `MODEL_DIR` and a batch size of 128. It also uses a timeout of 60 minutes. The `ModalEmbeddingFunction` class has a default batch size of 1024.

The `CPUEmbedding` class initializes a `SentenceTransformer` model and computes embeddings for a list of texts using the `encode` method. The `compute` method returns the computed embeddings.

The `chunk_string` function splits a string into sentences using regular expressions.

Overall, the code appears to be related to embedding functions and text processing.

## August 6, 2023
- Kevin: [Alerts: Minor Updates] We drastically decreased the rate of unimplemented functions in Sweep! 

This was done by improving how Sweep chooses what to modify as well as the self-review process, where it would correct itself when it doesn't fully implement a class or function. 

An example of this is at https://github.com/kevinlu1248/pyepsilla/pull/15 where Sweep had unimplemented changes but the self-review corrected itself.

The page is a pull request on GitHub titled "Create JavaScript/TypeScript client based on Python client" by sweep-canary[bot]. The pull request adds a JavaScript/TypeScript client for EpsillaDB, which is based on the functionality of the existing Python client. The new client includes a Client class in jsEpsilla/vectordb/client.ts that handles networking, makes requests, and processes responses. It also includes a Field class and a FieldType enum in jsEpsilla/vectordb/field.ts that mirror the functionality of the Python versions. The README.md file has been updated to include instructions on how to install and use the new JavaScript/TypeScript client, along with examples of how to use its methods. The pull request includes four commits and fixes issue #4.

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

## July 30, 2023
- We just launched external search! Sweep can now read the page of any link you reference in the issue title + description to publicly accessible URLs, including links to docs and PR's on open-source repos!
- We just launched external search! Sweep can now read the page of any link you reference in the issue title + description to publicly accessible URLs, including links to docs and PR's on open-source repos!

## July 29, 2023
- The search index now uses a higher quality retrieval embedding model!
- Streaming large files is now drastically faster!

## July 28, 2023
- You can now update the issue title or description, and Sweep will rewrite the ticket!

## July 27, 2023
- Slow mode! If you're using GPT4, you can tell Sweep to solve larger tasks.
- Moved code review step to before PR is created, so the PR you see initially should be higher quality. Also various prompt improvements for more consistent code modifications!

## July 26, 2023
- We just posted our blog "Letting an AI Junior Dev Run GitHub Actions" on HN.
- We just improved our search ranking again!

## July 25, 2023
- We've made drastic improvements to Sweep with Github Actions!

## July 24, 2023
- You can now tell Sweep more about your repository!
