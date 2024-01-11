from __future__ import annotations

import time
from enum import Enum
from threading import Thread

from loguru import logger
from openai import OpenAI
from openai.types.beta.threads.runs.code_tool_call import CodeToolCall
from openai.types.beta.threads.runs.function_tool_call import FunctionToolCall
from pydantic import BaseModel, Field

from sweepai.config.server import MONGODB_URI, OPENAI_API_KEY
from sweepai.core.entities import FileChangeRequest, Snippet
from sweepai.utils.chat_logger import discord_log_error, global_mongo_client


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
    assistant_id: str = ""
    run_id: str = ""
    thread_id: str = ""

    class Config:
        use_enum_values = True

    @classmethod
    def from_ids(
        cls,
        assistant_id: str,
        run_id: str,
        thread_id: str,
    ) -> AssistantConversation | None:
        client = OpenAI(api_key=OPENAI_API_KEY)
        try:
            assistant = client.beta.assistants.retrieve(
                assistant_id=assistant_id, timeout=1.5
            )
            run = client.beta.threads.runs.retrieve(
                run_id=run_id, thread_id=thread_id, timeout=1.5
            )
            message_objects = client.beta.threads.runs.steps.list(
                run_id=run_id, thread_id=thread_id, timeout=1.5
            ).data
        except:
            return None
        messages: list[AssistantAPIMessage] = [
            AssistantAPIMessage(
                role=AssistantAPIMessageRole.SYSTEM,
                content=assistant.instructions,
            )
        ]
        for message_obj in list(message_objects)[::-1]:
            if message_obj.type == "message_creation":
                message_id = message_obj.step_details.message_creation.message_id
                try:
                    message_content = (
                        client.beta.threads.messages.retrieve(
                            message_id=message_id, thread_id=thread_id, timeout=1.5
                        )
                        .content[0]
                        .text.value
                    )
                except:
                    return None
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
            assistant_id=assistant_id,
            run_id=run_id,
            thread_id=thread_id,
        )

    def update_from_ids(
        self,
        assistant_id: str,
        run_id: str,
        thread_id: str,
    ) -> AssistantConversation:
        assistant_conversation = AssistantConversation.from_ids(
            assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
        )
        if not assistant_conversation:
            return self
        self.messages = assistant_conversation.messages
        self.is_active = assistant_conversation.is_active
        self.status = assistant_conversation.status
        return self


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
    pruning_conversation_counter: int = 0
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
    branch_name: str = ""
    is_public: bool = True
    pr_id: int = -1
    start_time: int = 0
    done_time: int = 0
    payment_context: PaymentContext = PaymentContext()


class TicketUserStateTypes(Enum):
    RUNNING = "running"
    WAITING = "waiting"
    EDITING = "editing"


class TicketUserState(BaseModel):
    state_type: TicketUserStateTypes = TicketUserStateTypes.RUNNING
    waiting_deadline: int = 0

    class Config:
        use_enum_values = True


class TicketProgress(BaseModel):
    tracking_id: str
    username: str = ""
    context: TicketContext = TicketContext()
    status: TicketProgressStatus = TicketProgressStatus.SEARCHING
    search_progress: SearchProgress = SearchProgress()
    planning_progress: PlanningProgress = PlanningProgress()
    coding_progress: CodingProgress = CodingProgress()
    prev_dict: dict = Field(default_factory=dict)
    error_message: str = ""
    user_state: TicketUserState = TicketUserState()

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

    def _save(self):
        # Can optimize by only saving the deltas
        try:
            if MONGODB_URI is None:
                return None
            if self.dict() == self.prev_dict:
                return
            current_dict = self.dict()
            del current_dict["prev_dict"]
            self.prev_dict = current_dict
            db = global_mongo_client["progress"]
            collection = db["ticket_progress"]
            collection.update_one(
                {"tracking_id": self.tracking_id}, {"$set": current_dict}, upsert=True
            )
        except Exception as e:
            discord_log_error(str(e) + "\n\n" + str(self.tracking_id))

    def save(self, do_async: bool = True):
        if do_async:
            thread = Thread(target=self._save)
            thread.start()
        else:
            self._save()

    def wait(self, wait_time: int = 30):
        if MONGODB_URI is None:
            return
        try:
            # check if user set breakpoints
            current_ticket_progress = TicketProgress.load(self.tracking_id)
            current_ticket_progress.user_state = current_ticket_progress.user_state
            current_ticket_progress.user_state.state_type = TicketUserStateTypes.WAITING
            current_ticket_progress.user_state.waiting_deadline = (
                int(time.time()) + wait_time
            )
            current_ticket_progress.save(do_async=False)
            for i in range(10 * 60):
                current_ticket_progress = TicketProgress.load(self.tracking_id)
                user_state = current_ticket_progress.user_state
                if user_state.state_type == TicketUserStateTypes.RUNNING.value:
                    logger.info(f"Continuing...")
                    return
                if (
                    user_state.state_type == TicketUserStateTypes.WAITING.value
                    and user_state.waiting_deadline < int(time.time())
                ):
                    logger.info(f"Continuing...")
                    user_state.state_type = TicketUserStateTypes.RUNNING.value
                    return
                time.sleep(1)
                if i % 10 == 9:
                    logger.info(f"Waiting for user for {self.tracking_id}...")
            raise Exception("Timeout")
        except Exception as e:
            discord_log_error(
                "wait() method crashed with:\n\n"
                + str(e)
                + "\n\n"
                + str(self.tracking_id)
            )


def create_index():
    # killer code to make everything way faster
    db = global_mongo_client["progress"]
    collection = db["ticket_progress"]
    collection.create_index("tracking_id", unique=True)


if __name__ == "__main__":
    ticket_progress = TicketProgress(tracking_id="test")
    # ticket_progress.error_message = (
    #     "I'm sorry, but it looks like an error has occurred due to"
    #     + " a planning failure. Please create a more detailed issue"
    #     + " so I can better address it. Alternatively, reach out to Kevin or William for help at"
    #     + " https://discord.gg/sweep."
    # )
    # ticket_progress.status = TicketProgressStatus.ERROR
    # ticket_progress.save()
    ticket_progress.wait()
    # new_ticket_progress = TicketProgress.load("test")
    # print(new_ticket_progress)
    # assert new_ticket_progress == ticket_progress
