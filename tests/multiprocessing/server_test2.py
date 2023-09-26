import time

import requests


def start_task(key):
    response = requests.post(f"http://localhost:8000/start/{key}")
    return response.json()


def cancel_task(key):
    response = requests.post(f"http://localhost:8000/cancel/{key}")
    return response.json()


if __name__ == "__main__":
    task_key = "example_task"

    # Start a task
    for i in range(10):
        print(start_task(task_key))

    # Sleep for a while to let the task run
    time.sleep(2)

    # Start a task
    print(start_task(task_key))

    # Sleep for a while to let the task run
    time.sleep(2)

    # Cancel the task
    print(cancel_task(task_key))
