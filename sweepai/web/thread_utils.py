import ctypes

from loguru import logger


def terminate_thread(thread):
    """Terminate a python threading.Thread."""
    try:
        if not thread.is_alive():
            return

        exc = ctypes.py_object(SystemExit)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(thread.ident), exc
        )
        if res == 0:
            raise ValueError("Invalid thread ID")
        elif res != 1:
            # Call with exception set to 0 is needed to cleanup properly.
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
            raise SystemError("PyThreadState_SetAsyncExc failed")
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.exception(f"Failed to terminate thread: {e}")
