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


import datetime
import multiprocessing
import time
from unittest.mock import patch

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


class MockIssue:
    def __init__(self, created_at, labels, title):
        self.created_at = created_at
        self.labels = labels
        self.title = title


class MockPR:
    def __init__(self, created_at, labels, title):
        self.created_at = created_at
        self.labels = labels
        self.title = title


def delete_old_sweep_issues_and_prs():
    pass


def test_delete_old_sweep_issues_and_prs():
    with patch("sweepai.api.get_github_client") as mock_get_github_client:
        mock_github_client = mock_get_github_client.return_value
        mock_github_client.get_issues.return_value = [
            # Mock issues
            MockIssue(
                created_at=datetime.datetime.now() - datetime.timedelta(weeks=3),
                labels=["Sweep"],
                title="Sweep issue 1",
            ),
            MockIssue(
                created_at=datetime.datetime.now() - datetime.timedelta(weeks=1),
                labels=["Sweep"],
                title="Sweep issue 2",
            ),
            MockIssue(
                created_at=datetime.datetime.now() - datetime.timedelta(weeks=3),
                labels=[],
                title="Sweep issue 3",
            ),
            MockIssue(
                created_at=datetime.datetime.now() - datetime.timedelta(weeks=1),
                labels=[],
                title="Non-Sweep issue 1",
            ),
        ]
        mock_github_client.get_pulls.return_value = [
            # Mock PR's
            MockPR(
                created_at=datetime.datetime.now() - datetime.timedelta(weeks=3),
                labels=["Sweep"],
                title="Sweep PR 1",
            ),
            MockPR(
                created_at=datetime.datetime.now() - datetime.timedelta(weeks=1),
                labels=["Sweep"],
                title="Sweep PR 2",
            ),
            MockPR(
                created_at=datetime.datetime.now() - datetime.timedelta(weeks=3),
                labels=[],
                title="Sweep PR 3",
            ),
            MockPR(
                created_at=datetime.datetime.now() - datetime.timedelta(weeks=1),
                labels=[],
                title="Non-Sweep PR 1",
            ),
        ]
        delete_old_sweep_issues_and_prs()
        # Add assertions here to check that the correct issues and PR's were deleted
        assert mock_github_client.get_issues.call_count == 1
        assert mock_github_client.get_pulls.call_count == 1
        assert mock_github_client.create_issue_comment.call_count == 3
        assert mock_github_client.close_issue.call_count == 2
        assert mock_github_client.close_pr.call_count == 1
