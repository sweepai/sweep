client.chat_update(
                channel=request.channel_id,
                ts=searching_message["ts"],
                text=message,
            )
        else:
            snippets = []
        prompt = slack_slash_command_prompt.format(
            relevant_snippets="\n".join([snippet.xml for snippet in snippets]),
            relevant_directories="\n".join([snippet.file_path for snippet in snippets]),
            repo_name=repo_name,
            repo_description=repo.description,
            username=request.user_name,
            query=queries
        )
        response = sweep_bot.chat(prompt, functions=functions, function_name={"name": "create_pr"})
        logger.info(response)

        while sweep_bot.messages[-1].function_call is not None:
            obj = sweep_bot.messages[-1].function_call
            name = obj["name"]
            arguments = json.loads(obj["arguments"])
            if name == "get_relevant_snippets":
                logger.info("Searching for relevant snippets...")
                search_message = client.chat_postMessage(
                    channel=request.channel_id,
                    text=f":mag_right: Searching \"{arguments['query']}\" in the codebase...",
                    thread_ts=thread_ts
                )
                additional_snippets = sweep_bot.search_snippets(
                    [arguments["query"]],
                    installation_id=installation_id
                )
                # additional_snippets = default_snippets
                additional_snippets_message = f":mag_right: Found {len(additional_snippets)} additional snippets with the query \"{arguments['query']}\":\n\n" +  "\n".join(
                    f"{snippet.get_slack_link(repo_name)}\n```{snippet.get_preview()}

