class Messages:
    def __init__(self):
        self._messages = []
        self._system_prompt = None

    def __getitem__(self, index):
        return self._messages[index]

    def append(self, message):
        self._messages.append(message)

    def prompt(self, system_prompt, new_prompt, swap_prompt):
        return PromptContext(self, system_prompt, new_prompt, swap_prompt)


class PromptContext:
    def __init__(self, messages, system_prompt, new_prompt, swap_prompt):
        self._messages = messages
        self._system_prompt = system_prompt
        self._new_prompt = new_prompt
        self._swap_prompt = swap_prompt

    def __enter__(self):
        if self._swap_prompt:
            self._old_prompt = self._messages._system_prompt
            self._messages._system_prompt = self._new_prompt

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._swap_prompt:
            self._messages._system_prompt = self._old_prompt
