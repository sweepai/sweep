from __future__ import annotations

import time
from enum import Enum

from openai import OpenAI
from openai.types.beta.threads.runs.code_tool_call import CodeToolCall
from openai.types.beta.threads.runs.function_tool_call import FunctionToolCall
from pydantic import BaseModel, Field

from sweepai.config.server import MONGODB_URI, OPENAI_API_KEY
from sweepai.core.entities import FileChangeRequest, Snippet
from sweepai.utils.chat_logger import global_mongo_client


class AssistantAPIMessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    CODE_INTERPRETER_INPUT = "code_interpreter_input"
    CODE_INTERPRETER_OUTPUT = "code_interpreter_output"
    FUNCTION_CALL_INPUT = "function_call_input"
    FUNCTION_CALL_OUTPUT = "function_call_output"


class AssistantAPIMessage(BaseModel):
    class Config:
        use_enum_values = True

    role: AssistantAPIMessageRole
    content: str = ""


class AssistantStatus(Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    REQUIRES_ACTION = "requires_action"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"
    EXPIRED = "expired"


class AssistantConversation(BaseModel):
    messages: list[AssistantAPIMessage] = []
    is_active: bool = True
    status: AssistantStatus = "in_progress"

    class Config:
        use_enum_values = True

    @classmethod
    def from_ids(
        cls,
        assistant_id: str,
        run_id: str,
        thread_id: str,
    ) -> AssistantConversation:
        client = OpenAI(api_key=OPENAI_API_KEY)
        assistant = client.beta.assistants.retrieve(assistant_id=assistant_id)
        run = client.beta.threads.runs.retrieve(run_id=run_id, thread_id=thread_id)
        messages: list[AssistantAPIMessage] = [
            AssistantAPIMessage(
                role=AssistantAPIMessageRole.SYSTEM,
                content=assistant.instructions,
            )
        ]
        for message_obj in list(
            client.beta.threads.runs.steps.list(run_id=run_id, thread_id=thread_id).data
        )[::-1]:
            if message_obj.type == "message_creation":
                message_id = message_obj.step_details.message_creation.message_id
                message_content = (
                    client.beta.threads.messages.retrieve(
                        message_id=message_id, thread_id=thread_id
                    )
                    .content[0]
                    .text.value
                )
                messages.append(
                    AssistantAPIMessage(
                        role=AssistantAPIMessageRole.ASSISTANT,
                        content=message_content,
                    )
                )
                # TODO: handle annotations
            elif message_obj.type == "tool_calls":
                for tool_call in message_obj.step_details.tool_calls:
                    if isinstance(tool_call, CodeToolCall):
                        code_interpreter = tool_call.code_interpreter
                        input_ = code_interpreter.input
                        if not input_:
                            continue
                        messages.append(
                            AssistantAPIMessage(
                                role=AssistantAPIMessageRole.CODE_INTERPRETER_INPUT,
                                content=input_,
                            )
                        )
                        outputs = code_interpreter.outputs
                        output = outputs[0].logs if outputs else "__No output__"
                        messages.append(
                            AssistantAPIMessage(
                                role=AssistantAPIMessageRole.CODE_INTERPRETER_OUTPUT,
                                content=output,
                            )
                        )
                    elif isinstance(tool_call, FunctionToolCall):
                        messages.append(
                            AssistantAPIMessage(
                                role=AssistantAPIMessageRole.FUNCTION_CALL_INPUT,
                                content=tool_call.function.arguments,
                            )
                        )
                        messages.append(
                            AssistantAPIMessage(
                                role=AssistantAPIMessageRole.FUNCTION_CALL_OUTPUT,
                                content=tool_call.function.output or "__No output__",
                            )
                        )
        return cls(
            messages=messages,
            status=run.status,
            is_active=run.status not in ("succeeded", "failed"),
        )


class TicketProgressStatus(Enum):
    SEARCHING = "searching"
    PLANNING = "planning"
    CODING = "coding"
    COMPLETE = "complete"
    ERROR = "error"


class SearchProgress(BaseModel):
    class Config:
        use_enum_values = True

    indexing_progress: int = 0
    indexing_total: int = 0
    rephrased_query: str = ""
    retrieved_snippets: list[Snippet] = []
    final_snippets: list[Snippet] = []
    pruning_conversation: AssistantConversation = AssistantConversation()
    repo_tree: str = ""


class PlanningProgress(BaseModel):
    assistant_conversation: AssistantConversation = AssistantConversation()
    file_change_requests: list[FileChangeRequest] = []


class CodingProgress(BaseModel):
    file_change_requests: list[FileChangeRequest] = []
    assistant_conversations: list[AssistantConversation] = []


class PaymentContext(BaseModel):
    use_faster_model: bool = True
    pro_user: bool = True
    daily_tickets_used: int = 0
    monthly_tickets_used: int = 0


class TicketContext(BaseModel):
    title: str = ""
    description: str = ""
    repo_full_name: str = ""
    issue_number: int = 0
    is_public: bool = True
    pr_id: int = -1
    start_time: int = Field(default_factory=lambda: int(time.time()))
    payment_context: PaymentContext = PaymentContext()


class TicketProgress(BaseModel):
    tracking_id: str
    context: TicketContext = TicketContext()
    status: TicketProgressStatus = TicketProgressStatus.SEARCHING
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

    def save(self):  # might want a TTL
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
