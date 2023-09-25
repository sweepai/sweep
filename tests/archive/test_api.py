# import openai
# import asyncio
# from fastapi import Body, FastAPI
# from pydantic import BaseModel
# from sweepai.core.chat import ChatGPT

# app = FastAPI()
# tasks = {}


# async def background_task(name: str):
#     # import os
#     # print(os.getpid())
#     # import random
#     # print(random.random())
#     import os, hashlib
#     random_bytes = os.urandom(16)
#     hash_obj = hashlib.sha256(random_bytes)
#     hash_hex = hash_obj.hexdigest()

#     print(hash_hex)
#     print("Starting background task")
#     for i in range(1, 6):
#         print(f"Task {name} running ({i}/5)...")
#         await asyncio.sleep(1)
#     print(f"Task {name} completed.")


# class Task(BaseModel):
#     name: str


# @app.post("/start")
# async def start_task(request: Task):
#     task = asyncio.create_task(background_task(request.name))
#     tasks[request.name] = task
#     return {"message": "Task started"}


# @app.post("/cancel")
# async def cancel_task(request: Task):
#     task = tasks.get(request.name)
#     if task:
#         task.cancel()
#         return {"message": "Task canceled"}
#     return {"message": "Task not found"}


from fastapi import FastAPI
import multiprocessing
import time

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
