def modify_file(
        self, 
        file_change_request: FileChangeRequest, 
        contents: str = "", 
        contents_line_numbers: str = "", 
        branch=None, 
        chunking: bool = False,
        chunk_offset: int = 0,
        chunk_size: int = 1024
) -> tuple[str, str]:
    for count in range(5):
        key = f"file_change_modified_{file_change_request.filename}"
        file_markdown = is_markdown(file_change_request.filename)
        try:
            message = modify_file_prompt_2.format(
                    filename=file_change_request.filename,
                    instructions=file_change_request.instructions,
                    code=contents_line_numbers,
                    line_count=contents.count('\n') + 1
                )
            if chunking:
                message = chunking_prompt + message
                modify_file_response = self.chat(
                    message,
                    message_key=key,
                )
                self.delete_messages_from_chat(key)
            else:
                modify_file_response = self.chat(
                    message,
                    message_key=key,
                )
        except Exception as e: # Check for max tokens error
            if "max tokens" in str(e).lower():
                logger.error(f"Max tokens exceeded for {file_change_request.filename}")
                raise MaxTokensExceeded(file_change_request.filename)
        try:
            logger.info(f"generate_new_file with contents: {contents} and modify_file_response: {modify_file_response}")
            new_file = generate_new_file(modify_file_response, contents, chunk_offset=chunk_offset)
            if not is_markdown(file_change_request.filename):
                code_repairer = CodeRepairer(chat_logger=self.chat_logger)
                diff = generate_diff(old_code=contents, new_code=new_file)
                if diff.strip() != "" and diff_contains_dups_or_removals(diff, new_file):
                    new_file = code_repairer.repair_code(diff=diff, user_code=new_file,
                                                            feature=file_change_request.instructions)
            new_file = format_contents(new_file, file_markdown)
            new_file = new_file.rstrip()
            if contents.endswith("\n"):
                new_file += "\n"
            return new_file
        except Exception as e:
            tb = traceback.format_exc()
            logger.warning(f"Recieved error {e}\n{tb}")
            logger.warning(
                f"Failed to parse. Retrying for the {count}th time..."
            )
            self.delete_messages_from_chat(key)
            continue
    raise Exception("Failed to parse response after 5 attempts.")