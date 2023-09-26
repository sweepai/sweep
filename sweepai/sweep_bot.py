# sweepai/sweep_bot.py

class UnneededEditError(Exception):
    def __init__(self, message):
        super().__init__(message)


class MatchingError(Exception):
    def __init__(self, message):
        super().__init__(message)


class ModifyBot:
    # existing code...

    def some_method(self):
        # existing code...

        # Replace assert statement with UnneededEditError
        if not condition1:  # condition1 checks if there are no occurrences of the snippet in the generated XML
            raise UnneededEditError("No occurrences of the snippet in the generated XML")

        # existing code...

        # Replace assert statement with MatchingError
        if not condition2:  # condition2 checks if there are no more snippets after matching
            raise MatchingError("No more snippets after matching")

        # existing code...
