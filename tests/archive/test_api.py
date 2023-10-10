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


import unittest
from unittest.mock import patch, MagicMock
from sweepai.api import delete_old_issues_and_prs

class TestDeleteOldIssuesAndPrs(unittest.TestCase):
    @patch('github.Github')
    def test_delete_old_issues_and_prs(self, mock_github):
        # Mock the Github API
        mock_github.return_value.get_repo.return_value.get_issues.return_value = [
            MagicMock(created_at=datetime.datetime.now() - datetime.timedelta(days=15), labels=['Sweep'], title='Sweep issue 1'),
            MagicMock(created_at=datetime.datetime.now() - datetime.timedelta(days=10), labels=['Sweep'], title='Sweep issue 2'),
            MagicMock(created_at=datetime.datetime.now() - datetime.timedelta(days=20), labels=[], title='Non-Sweep issue'),
            MagicMock(created_at=datetime.datetime.now() - datetime.timedelta(days=5), labels=['Sweep'], title='Sweep issue 3'),
        ]
        
        mock_github.return_value.get_repo.return_value.get_pulls.return_value = [
            MagicMock(created_at=datetime.datetime.now() - datetime.timedelta(days=15), labels=['Sweep'], title='Sweep PR 1'),
            MagicMock(created_at=datetime.datetime.now() - datetime.timedelta(days=10), labels=['Sweep'], title='Sweep PR 2'),
            MagicMock(created_at=datetime.datetime.now() - datetime.timedelta(days=20), labels=[], title='Non-Sweep PR'),
            MagicMock(created_at=datetime.datetime.now() - datetime.timedelta(days=5), labels=['Sweep'], title='Sweep PR 3'),
        ]

        # Call the delete_old_issues_and_prs function
        delete_old_issues_and_prs()

        # Assert that the function deleted the correct issues and PR's and left a comment on each one before deleting it
        for issue in mock_github.return_value.get_repo.return_value.get_issues.return_value:
            if (datetime.datetime.now() - issue.created_at).days > 14 and ('Sweep' in issue.labels or issue.title.startswith('Sweep')):
                issue.create_comment.assert_called_once_with('This issue is over two weeks old and will be deleted.')
                issue.edit.assert_called_once_with(state='closed')
            else:
                issue.create_comment.assert_not_called()
                issue.edit.assert_not_called()
                
        for pr in mock_github.return_value.get_repo.return_value.get_pulls.return_value:
            if (datetime.datetime.now() - pr.created_at).days > 14 and ('Sweep' in pr.labels or pr.title.startswith('Sweep')):
                pr.create_issue_comment.assert_called_once_with('This PR is over two weeks old and will be deleted.')
                pr.edit.assert_called_once_with(state='closed')
            else:
                pr.create_issue_comment.assert_not_called()
                pr.edit.assert_not_called()

if __name__ == '__main__':
    unittest.main()
