def file_names_change(file_names):
        global selected_snippets
        global file_to_str
        global path_to_contents
        selected_snippets = [Snippet(content=path_to_contents[file_name], start=0, end=path_to_contents[file_name].count('\n'), file_path=file_name) for file_name in file_names]
        return file_names, build_string()
    
    file_names.change(file_names_change, [file_names], [file_names, snippets_text])
    
    def handle_message_submit(repo_full_name: str, user_message: str, history: list[tuple[str | None, str | None]]):
        if not repo_full_name:
            raise Exception("Set the repository name first")
        return gr.update(value="", interactive=False), history + [[user_message, None]]

    def handle_message_stream(chat_history: list[tuple[str | None, str | None]], snippets_text, file_names):
        global selected_snippets
        global searched
        message = chat_history[-1][0]
        yield chat_history, snippets_text, file_names
        if not selected_snippets:
            searched = True
            # Searching for relevant snippets
            chat_history[-1][1] = "Searching for relevant snippets..."
            snippets_text = build_string()
            yield chat_history, snippets_text, file_names
            logger.info("Fetching relevant snippets...")
            selected_snippets += api_client.search(chat_history[-1][0], 3)
            snippets_text = build_string()
            file_names = [snippet.file_path for snippet in selected_snippets]
            yield chat_history, snippets_text, file_names
            logger.info("Fetched relevant snippets.")
            chat_history[-1][1] = "Found relevant snippets."
            # Update using chat_history
            snippets_text = build_string()
            yield chat_history, snippets_text, file_names
        
        global proposed_pr
        if proposed_pr and chat_history[-1][0].strip().lower() in ("okay", "ok"):
            chat_history[-1][1] = f"⏳ Creating PR..."
            yield chat_history, snippets_text, file_names
            pull_request = api_client.create_pr(
                file_change_requests=[(item["file_path"], item["instructions"]) for item in proposed_pr["plan"]],
                pull_request={
                    "title": proposed_pr["title"],
                    "content": proposed_pr["summary"],
                    "branch_name": proposed_pr["branch"],
                },
                messages=chat_history,
            )
            chat_history[-1][1] = f"✅ PR created at {pull_request['html_url']}"
            yield chat_history, snippets_text, file_names
            return

        # Generate response
        logger.info("...")
        chat_history.append([None, "..."])
        yield chat_history, snippets_text, file_names
        chat_history[-1][1] = ""
        logger.info("Starting to generate response...")
        if len(chat_history) > 1 and "create pr" in message.lower():
            stream = api_client.stream_chat(
                chat_history, 
                selected_snippets,
                functions=[create_pr_function],
                function_call=create_pr_function_call,
            )
        else:
            stream = api_client.stream_chat(chat_history, selected_snippets)
        function_name = ""
        raw_arguments = ""
        for chunk in stream:
            if chunk.get("content"):
                token = chunk["content"]
                chat_history[-1][1] += token
                yield chat_history, snippets_text, file_names
            if chunk.get("function_call"):
                function_call = chunk["function_call"]
                function_name = function_name or function_call.get("name")
                raw_arguments += function_call.get("arguments")
                chat_history[-1][1] = f"Calling function: `{function_name}`\n```json\n{raw_arguments}\n

