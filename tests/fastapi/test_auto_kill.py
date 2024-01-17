import ctypes
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from time import sleep

from fastapi import FastAPI

app = FastAPI()

tasks = {}
executor = ThreadPoolExecutor(max_workers=4)


def long_running_task(task_id):
    try:
        print("Start")
        for i in range(10):
            print(i)
            sleep(1)
        tasks[task_id] = "Done"
        print("Done")
    except SystemExit:
        print("SystemExit")
        raise SystemExit
    except Exception as e:
        print("Exception")
        print(e)
        raise e


def terminate_thread(thread):
    """Terminate a python threading.Thread."""
    try:
        if not thread.is_alive():
            print("Thread already terminated")
            return

        exc = ctypes.py_object(SystemExit)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(thread.ident), exc
        )
        if res == 0:
            print("Invalid thread ID")
            raise ValueError("Invalid thread ID")
        elif res != 1:
            print("PyThreadState_SetAsyncExc failed")
            # Call with exception set to 0 is needed to cleanup properly.
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
            raise SystemError("PyThreadState_SetAsyncExc failed")
    except SystemExit:
        print("SystemExit")
        raise SystemExit
    except Exception as e:
        print(f"Failed to terminate thread: {e}")


def delayed_kill(thread):
    sleep(3)
    terminate_thread(thread)


@app.post("/start/")
def start_task():
    task_id = str(uuid.uuid4())
    thread = threading.Thread(target=long_running_task, args=(task_id,))
    thread.start()

    # delayed_kill_thread = threading.Thread(target=delayed_kill, args=(thread,))
    # delayed_kill_thread.start()

    return {"task_id": task_id}


@app.get("/list/")
def list_tasks():
    print(tasks)
    return tasks
