class UnneededEditError(Exception):
    """
    Exception raised when an edit is not needed.
    """
    def __init__(self, message: str):
        super().__init__(message)


class MatchingError(Exception):
    """
    Exception raised when there is a matching error.
    """
    def __init__(self, message: str):
        super().__init__(message)
