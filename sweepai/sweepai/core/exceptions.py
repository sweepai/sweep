class UnneededEditError(Exception):
    """
    Exception raised when an unneeded edit is detected.
    """
    def __init__(self, message):
        super().__init__(message)


class MatchingError(Exception):
    """
    Exception raised when a matching error occurs.
    """
    def __init__(self, message):
        super().__init__(message)
