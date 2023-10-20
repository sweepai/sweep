import threading

def run_in_worker(func, args):
    """
    Runs a given function in a new thread with the provided arguments.

    Args:
        func (function): The function to run in a new thread.
        args (dict): The arguments to pass to the function.

    Returns:
        None
    """
    thread = threading.Thread(target=func, kwargs=args)
    thread.start()
