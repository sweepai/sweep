def fire_and_forget_wrapper(call):
    """
    This decorator is used to run a function in a separate thread.
    It does not return anything and does not wait for the function to finish.
    It fails silently.
    """

    def wrapper(*args, **kwargs):
        try:
            return call(*args, **kwargs)
        except Exception:
            pass

    return wrapper