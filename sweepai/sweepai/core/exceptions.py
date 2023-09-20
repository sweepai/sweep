class UnneededEditError(Exception):
    def __init__(self, message="Unneeded edit error occurred"):
        super().__init__(message)


class MatchingError(Exception):
    def __init__(self, message="Matching error occurred"):
        super().__init__(message)
