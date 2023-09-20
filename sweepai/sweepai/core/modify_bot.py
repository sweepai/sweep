class UnneededEditError(Exception):
    def __init__(self, message="Unneeded edit detected"):
        super().__init__(message)


class MatchingError(Exception):
    def __init__(self, message="No more snippets after matching"):
        super().__init__(message)
