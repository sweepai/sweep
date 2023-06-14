from loguru import logger
import modal
from pydantic import ValidationError  # type: ignore

from src.handlers.on_ticket import on_ticket
from src.handlers.on_comment import on_comment
from src.events import CommentCreatedRequest, IssueRequest  # noqa: F401
from fastapi import HTTPException, Request

stub = modal.Stub("handle-ticket")
image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install("openai", "PyGithub", "loguru")
)
secrets = [
    modal.Secret.from_name("bot-token"),
    modal.Secret.from_name("openai-secret"),
]

handle_ticket = stub.function(image=image, secrets=secrets)(on_ticket)
handle_comment = stub.function(image=image, secrets=secrets)(on_comment)


@stub.webhook(method="POST", image=image, secrets=secrets)
async def handle_ticket_webhook(raw_request: Request):
    """Handle a webhook request from GitHub."""
    try:
        request_dict = await raw_request.json()
        logger.info(f"Received request: {request_dict.keys()}")
        event = raw_request.headers.get("X-GitHub-Event")
        assert event is not None
        match event, request_dict.get("action", None):
            case ("issues", "opened") | ("issues", "assigned"):
                request = IssueRequest(**request_dict)
                if (
                    request.issue is not None
                    and (
                        request.action == "opened"
                        or (
                            request.action == "assigned"
                            and request.assignee is not None
                            and request.assignee.login == "sweepaibot"
                        )
                        or "sweep" in [label.lower() for label in request.issue.labels]
                    )
                    and request.issue.assignees
                    and "sweepaibot"
                    in [assignee.login for assignee in request.issue.assignees]
                ):
                    request.issue.body = request.issue.body or ""
                    request.repository.description = (
                        request.repository.description or ""
                    )
                    handle_ticket.spawn(
                        request.issue.title,
                        request.issue.body,
                        request.issue.number,
                        request.issue.html_url,
                        request.issue.user.login,
                        request.repository.full_name,
                        request.repository.description,
                        request.installation.id,
                    )
            # case "pull_request_review_comment", "created":
            #     request = CommentCreatedRequest(**request_dict)
            #     handle_comment.spawn(
            #         request.issue.title,
            #         request.issue.body,
            #         request.issue.number,
            #         request.issue.html_url,
            #         request.issue.user.login,
            #         request.repository.full_name,
            #         request.repository.description,
            #     )
            case "installation", "created":
                pass
            case "ping", None:
                return {"message": "pong"}
            case _:
                logger.error(f"Unhandled event: {event} {request_dict['action']}")
                raise HTTPException(
                    status_code=422,
                    detail=f"Unhandled event: {event} {request_dict['action']}",
                )
    except ValidationError as e:
        logger.error(f"Failed to parse request: {e}")
        raise HTTPException(status_code=422, detail="Failed to parse request")
    return {"success": True}
