class Messages(list):
    def __init__(self, *args):
        super().__init__(*args)
        self.original_prompt = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.original_prompt is not None:
            self.prompt(self.original_prompt)

    def prompt(self, system_prompt, new_prompt, swap_prompt=True):
        class PromptContext:
            def __init__(self, messages, system_prompt, new_prompt):
                self.messages = messages
                self.system_prompt = system_prompt
                self.new_prompt = new_prompt

            def __enter__(self):
                if swap_prompt:
                    self.messages.original_prompt = self.system_prompt
                    self.messages.prompt = self.new_prompt
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.messages.original_prompt is not None:
                    self.messages.prompt = self.messages.original_prompt
                    self.messages.original_prompt = None

        return PromptContext(self, system_prompt, new_prompt)

    def to_openai(self):
        return [message.to_openai() for message in self]
