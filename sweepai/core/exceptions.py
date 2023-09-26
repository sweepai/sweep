class UnneededEditError(Exception):
    def __init__(self, message):
        super().__init__(message)


class MatchingError(Exception):
    def __init__(self, message):
        super().__init__(message)
