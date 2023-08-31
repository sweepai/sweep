import openai
import asyncio
from fastapi import Body, FastAPI
from pydantic import BaseModel
from sweepai.core.chat import ChatGPT

# app = FastAPI()
# tasks = {}


# async def background_task(name: str):
#     print("Starting background task")
#     chat = ChatGPT.from_system_message_string("You are a helpful assistant.", None)
#     print("Background task started")
#     for i in range(1, 4):
#         print(f"Task {name} running ({i}/3)...")
#         await chat.achat("This is a test.")
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
from concurrent.futures import ThreadPoolExecutor, Future
import time


app = FastAPI()
executor = ThreadPoolExecutor(max_workers=10)
futures_dict = {}


def long_task(key):
    print(f"Start task {key}")
    time.sleep(3)
    print(f"Mid task {key}")
    time.sleep(3)
    print(f"End task {key}")
    return f"Done {key}"

async def background_task(name: str):
    await asyncio.sleep(10)
    print(f"Task {name} completed.")

@app.post("/start/{key}")
async def start_task(key: str):
    print(futures_dict)
    if key in futures_dict:
        futures_dict[key].cancel()

    future = executor.submit(long_task, key)
    futures_dict[key] = future

    return {"status": "started"}


@app.post("/cancel/{key}")
async def cancel_task(key: str):
    if key in futures_dict:
        futures_dict[key].cancel()
        del futures_dict[key]
        return {"status": "cancelled"}

    return {"status": "not_found"}
