import multiprocessing
import time

from fastapi import FastAPI

app = FastAPI()
processes_dict = {}


def long_task(key):
    for i in range(100):
        print(f"{key}", i)
        time.sleep(1)


def start_task(key):
    print(processes_dict)
    if key in processes_dict:
        processes_dict[key].terminate()
        processes_dict[key].join()
        print("Terminated ", key)

    process = multiprocessing.Process(target=long_task, args=(key,))
    processes_dict[key] = process
    process.start()

    return {"status": "started"}


def cancel_task(key):
    if key in processes_dict:
        process = processes_dict[key]
        process.terminate()
        process.join()
        del processes_dict[key]
        return {"status": "cancelled"}

    return {"status": "not_found"}


@app.post("/start/{key}")
async def start_task_endpoint(key: str):
    return start_task(key)


@app.post("/cancel/{key}")
async def cancel_task_endpoint(key: str):
    return cancel_task(key)


# uvicorn server_test:app --host 0.0.0.0 --port 8000
