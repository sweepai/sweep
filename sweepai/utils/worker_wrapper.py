import threading

from loguru import logger


class WorkerWrapper:
    """
    A class that runs a given function in a separate worker thread.

    Example usage:

    def my_function(arg1, arg2):
        # Do something
        pass

    worker = WorkerWrapper(my_function, arg1, arg2)
    worker.start()
    """

    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.thread = threading.Thread(target=self.run)

    def run(self):
        try:
            self.func(*self.args, **self.kwargs)
        except Exception as e:
            logger.exception(f"Exception occurred in worker thread: {e}")

    def start(self):
        self.thread.start()

    def join(self):
        self.thread.join()
