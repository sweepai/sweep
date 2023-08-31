import openai
import asyncio
from fastapi import Body, FastAPI
from pydantic import BaseModel
from sweepai.core.chat import ChatGPT

app = FastAPI()
tasks = {}


async def background_task(name: str):
    print("Starting background task")
    chat = ChatGPT.from_system_message_string("You are a helpful assistant.", None)
    print("Background task started")
    for i in range(1, 4):
        print(f"Task {name} running ({i}/3)...")
        await chat.achat("This is a test.")
    print(f"Task {name} completed.")


class Task(BaseModel):
    name: str


@app.post("/start")
async def start_task(request: Task):
    task = asyncio.create_task(background_task(request.name))
    tasks[request.name] = task
    return {"message": "Task started"}


@app.post("/cancel")
async def cancel_task(request: Task):
    task = tasks.get(request.name)
    if task:
        task.cancel()
        return {"message": "Task canceled"}
    return {"message": "Task not found"}
