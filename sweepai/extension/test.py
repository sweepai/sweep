import ctypes
import time
import threading


class ContextManager:
    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        pass


class Obj:
    def __del__(self):
        pass


# Create new function and thread
def new_function():
    try:
        obj = Obj()
        with open("test.txt", "w") as f:
            while True:
                time.sleep(1)
                print("hi")
        print("done")
    except SystemExit:
        raise SystemExit
    except:
        print("death")


t = threading.Thread(target=new_function)
t.start()


import logging
import traceback

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
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
            raise SystemError("PyThreadState_SetAsyncExc failed")
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logging.error(f"Failed to terminate thread: {e}, {traceback.format_exc()}")