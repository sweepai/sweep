import queue
import time
from queue import Queue
from threading import Thread

from fastapi import FastAPI

from sweepai.utils.safe_dictionary import SafeDictionary

app = FastAPI()


user_queues: dict[str, Queue] = SafeDictionary()
active_workers: dict[str, 0] = SafeDictionary()


def process_queue(username):
    while True:
        user_queue = user_queues.get(username)
        if user_queue is None:
            break

        try:
            task = user_queue.get(timeout=2)
        except queue.Empty:
            if user_queues[username].empty():
                active_workers[username] = active_workers.get(username, 0) - 1
                break
            continue

        print(f"Processing task for {username}: {task}")
        try:
            time.sleep(3)  # Simulate task processing
        except Exception as e:
            print(f"Exception {e}!")
        print(f"Task completed for {username}: {task}")
        for key, value in user_queues.items():
            print(key, value.qsize())
        print(active_workers._dict)
        user_queue.task_done()


def start_user_workers(username, num_workers=1):
    for _ in range(num_workers):
        worker_thread = Thread(target=process_queue, args=(username,))
        worker_thread.start()
        active_workers[username] = active_workers.get(username, 0) + 1


def calculate_num_workers(username):
    # Temporary way to determine num workers
    return len(username)


@app.post("/task/{username}")
def add_task(username: str, task: str):
    num_allowed_workers = calculate_num_workers(username)
    if username not in user_queues:
        user_queues[username] = Queue()
    user_queues[username].put(task)
    start_user_workers(
        username,
        num_workers=min(num_allowed_workers, user_queues[username].qsize() + 1)
        - active_workers.get(username, 0),
    )
    for key, value in user_queues.items():
        print(key, value.qsize())
    print(active_workers._dict)
    return {"message": f"Task queued for {username}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
