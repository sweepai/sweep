import time
from queue import Queue
from threading import Lock, Thread

from fastapi import FastAPI

app = FastAPI()

user_queues: dict[str, Queue] = {}
user_queues_lock = Lock()

active_workers: dict[str, int] = {}


def process_queue(username):
    while True:
        with user_queues_lock:
            user_queue = user_queues.get(username)
        if user_queue and not user_queue.empty():
            task = user_queue.get()
            print(f"Processing task for {username}: {task}")
            time.sleep(3)
            print(f"Task completed for {username}: {task}")
            user_queue.task_done()
        else:
            with user_queues_lock:
                del user_queues[username]
            break


def start_user_workers(username, num_workers=1):
    for _ in range(num_workers):
        worker_thread = Thread(target=process_queue, args=(username,))
        worker_thread.start()
        with user_queues_lock:
            active_workers[username] = active_workers.get(username, 0) + 1


@app.post("/task/{username}")
def add_task(username: str, task: str):
    with user_queues_lock:
        if username not in user_queues:
            user_queues[username] = Queue()
            start_user_workers(username, 1)
        elif active_workers[username] < 2:
            start_user_workers(username, 1)
        user_queues[username].put(task)
        if username not in user_queues:
            start_user_workers(username, MAX_WORKERS_PER_USER)
        user_queues[username].put(task)
    return {"message": f"Task queued for {username}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
