import asyncio
from time import sleep
from fastapi import Body, FastAPI
from pydantic import BaseModel

app = FastAPI()
tasks = {}


async def background_task(name: str):
    for i in range(1, 10):
        print(f"Task {name} running ({i}/5)...")
        # await asyncio.sleep(1)
        sleep(1)
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
