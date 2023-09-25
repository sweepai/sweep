import threading
import time
import ctypes

events = {}


def terminate_thread(thread):
    """Terminate a python threading.Thread."""
    if not thread.is_alive():
        return

    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident), exc)
    if res == 0:
        raise ValueError("Invalid thread ID")
    elif res != 1:
        # Call with exception set to 0 is needed to cleanup properly.
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
        raise SystemError("PyThreadState_SetAsyncExc failed")


def run_comment(*args, **kwargs):
    i = 0
    while True:
        # Simulate some task
        print("Thread is running", i)
        i += 1
        time.sleep(1)


def call_on_comment(*args, **kwargs):
    global events
    repo_full_name = kwargs["repo_full_name"]
    pr_id = kwargs["pr_number"]
    key = f"{repo_full_name}-{pr_id}"

    # Check if a previous process exists for the same key, cancel it
    thread = events.get(key, None)
    if thread:
        terminate_thread(thread)

    thread = threading.Thread(target=run_comment, args=args, kwargs=kwargs)
    events[key] = thread
    thread.start()


# Example usage
call_on_comment(repo_full_name="exampleRepo", pr_number=1)
time.sleep(5)
call_on_comment(repo_full_name="exampleRepo", pr_number=1)
