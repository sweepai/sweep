from typing import Optional, Literal, TypedDict

class CheckStatus(TypedDict):
    message: str
    stdout: str
    succeeded: Optional[bool]
    status: Literal["pending", "running", "success", "failure", "cancelled"]
    llm_message: str
    container_name: str

# Status can be one of: completed, action_required, cancelled, failure, neutral, skipped, stale, success, timed_out, in_progress, queued, requested, waiting, pending.
gha_to_check_status = {
    "completed": "success",
    "action_required": "success",
    "cancelled": "cancelled",
    "failure": "failure",
    "neutral": "success",
    "skipped": "success",
    "stale": "success",
    "success": "success",
    "timed_out": "failure",
    "in_progress": "running",
    "queued": "pending",
    "requested": "pending",
    "waiting": "pending",
    "pending": "pending",
}

gha_to_succeeded = {
    "completed": True,
    "action_required": False,
    "cancelled": False,
    "failure": False,
    "neutral": True,
    "skipped": True,
    "stale": True,
    "success": True,
}

gha_to_message = {
    "completed": "Github Action completed",
    "action_required": "Github Action action required",
    "cancelled": "Github Action cancelled",
    "failure": "Github Action failed",
    "neutral": "Github Action neutral",
    "skipped": "Github Action skipped",
    "stale": "Github Action stale",
    "success": "Github Action succeeded",
    "timed_out": "Github Action timed out",
    "in_progress": "Github Action in progress",
    "queued": "Github Action queued",
    "requested": "Github Action requested",
    "waiting": "Github Action waiting",
    "pending": "Github Action pending",
}
