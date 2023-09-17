import ctypes
import time
import threading


class ContextManager:
    def __enter__(self):
        print("enter")

    def __exit__(self, type, value, traceback):
        print(type, value, traceback)
        print("exit")


class Obj:
    def __del__(self):
        print("deleted!")


# Create new function and thread
def new_function():
    try:
        obj = Obj()
        with open("test.txt", "w") as f:
            while True:
                # sleep
                time.sleep(1)
                print("hi")
            # f.write("Hello world!")
        print("done")
    except SystemExit:
        raise SystemExit
    except:
        print("death")


t = threading.Thread(target=new_function)
t.start()


def terminate_thread(thread):
    """Terminate a python threading.Thread."""
    # Todo(lukejagg): for multiprocessing, see if .terminate is catched in try/catch
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
        print(f"Failed to terminate thread: {e}")


time.sleep(4)
terminate_thread(t)
