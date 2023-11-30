from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from sweepai.config.server import MONGODB_URI
from sweepai.core.entities import FileChangeRequest, Snippet
from sweepai.utils.chat_logger import global_mongo_client


class AssistantAPIMessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    CODE_INTERPRETER_INPUT = "code_interpreter_input"
    CODE_INTERPRETER_OUTPUT = "code_interpreter_output"
    FUNCTION_CALL = "function_call"


class AssistantAPIMessage(BaseModel):
    role: AssistantAPIMessageRole
    content: str = ""


class AssistantConversation(BaseModel):
    messages: list[str] = []
    is_active: bool = True


class Status(Enum):
    SEARCHING = "searching"
    PLANNING = "planning"
    CODING = "coding"
    COMPLETE = "complete"
    ERROR = "error"


class SearchProgress(BaseModel):
    indexing_progress: int = 0
    indexing_total: int = 0
    rephrased_query: str = ""
    retrieved_snippets: list[Snippet] = []
    final_snippets: list[Snippet] = []


class PlanningProgress(BaseModel):
    assistant_conversation: AssistantConversation = AssistantConversation()


class CodingProgress(BaseModel):
    file_change_requests: list[tuple[FileChangeRequest, AssistantConversation]] = []


class Context(BaseModel):
    title: str = ""
    description: str = ""
    repo_full_name: str = ""
    issue_number: int = 0
    pr_id: int = -1


class TicketProgress(BaseModel):
    tracking_id: str
    context: Context = Context()
    status: Status = Status.SEARCHING
    search_progress: SearchProgress = SearchProgress()
    planning_progress: PlanningProgress = PlanningProgress()
    coding_progress: CodingProgress = CodingProgress()
    error_message: str = ""

    class Config:
        use_enum_values = True

    @classmethod
    def load(cls, tracking_id: str) -> TicketProgress:
        if MONGODB_URI is None:
            return None
        db = global_mongo_client["progress"]
        collection = db["ticket_progress"]
        doc = collection.find_one({"tracking_id": tracking_id})
        return cls(**doc)

    def save(self):
        if MONGODB_URI is None:
            return None
        db = global_mongo_client["progress"]
        collection = db["ticket_progress"]
        collection.update_one(
            {"tracking_id": self.tracking_id}, {"$set": self.dict()}, upsert=True
        )


if __name__ == "__main__":
    ticket_progress = TicketProgress(tracking_id="test")
    ticket_progress.save()
    new_ticket_progress = TicketProgress.load("test")
    print(new_ticket_progress)
    assert new_ticket_progress == ticket_progress
