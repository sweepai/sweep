import ctypes
import threading
import time

from sweepai.logn import logger


def terminate_thread(thread: threading.Thread):
    """Terminates a python thread from another thread."""
    if not thread.is_alive():
        return
    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident), exc)
    if res == 0:
        raise ValueError("nonexistent thread id")
    elif res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


def delayed_kill(thread: threading.Thread, delay: int = 60 * 60):
    """
    This function takes a thread and a delay as input, waits for the delay, and then terminates the thread.
    """
    time.sleep(delay)
    terminate_thread(thread)


on_ticket_events = {}


def run_on_ticket(*args, **kwargs):
    """This function will run the ticket."""
    # Implement the function here


def call_on_ticket(*args, **kwargs):
    """
    This function takes various arguments, creates a key from the repo full name and issue number, checks if a previous process exists for the same key and cancels it if it does, and then starts a new thread for the ticket. It also starts a delayed kill thread for the new thread.
    """
    global on_ticket_events
    key = f"{kwargs['repo_full_name']}-{kwargs['issue_number']}"  # Full name, issue number as key

    # Use multithreading
    # Check if a previous process exists for the same key, cancel it
    e = on_ticket_events.get(key, None)
    if e:
        logger.info(f"Found previous thread for key {key} and cancelling it")
        terminate_thread(e)

    thread = threading.Thread(target=run_on_ticket, args=args, kwargs=kwargs)
    on_ticket_events[key] = thread
    thread.start()

    delayed_kill_thread = threading.Thread(target=delayed_kill, args=(thread,))
    delayed_kill_thread.start()
