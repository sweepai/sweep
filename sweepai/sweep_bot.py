class UnneededEditError(Exception):
    def __init__(self, message="Unneeded edit error"):
        super().__init__(message)


class MatchingError(Exception):
    def __init__(self, message="Matching error"):
        super().__init__(message)


class ModifyBot:
    def __init__(self, ...):
        ...

    def some_method(self, ...):
        ...
        # Replace assert statement with UnneededEditError
        if not occurrences_of_snippet_in_generated_xml:
            raise UnneededEditError("No occurrences of snippet in the generated XML")

        ...
        # Replace assert statement with MatchingError
        if not more_snippets_after_matching:
            raise MatchingError("No more snippets after matching")

        ...
