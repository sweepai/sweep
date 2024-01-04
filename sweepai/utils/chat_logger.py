import json
from datetime import datetime, timedelta
from threading import Thread
from typing import Any

import requests
from pydantic import BaseModel, Field
from pymongo import MongoClient

from sweepai.config.server import (
    DISCORD_LOW_PRIORITY_URL,
    DISCORD_MEDIUM_PRIORITY_URL,
    DISCORD_WEBHOOK_URL,
    GITHUB_BOT_USERNAME,
    MONGODB_URI,
)
from sweepai.logn import logger

global_mongo_client = MongoClient(
    MONGODB_URI, serverSelectionTimeoutMS=20000, socketTimeoutMS=20000
)


class ChatLogger(BaseModel):
    data: dict
    chat_collection: Any = None
    ticket_collection: Any = None
    _ticket_count_cache = {}
    _user_field_cache = {}
    expiration: datetime = None
    index: int = 0
    current_date: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%m/%Y/%d")
    )
    current_month: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%m/%Y")
    )
    active: bool = False  # refers to whether it was an auto-created PR or if it was created by the user with intent

    def __init__(self, data: dict[str, str] = {}, mock=False, **kwargs):
        super().__init__(data=data, **kwargs)
        key = MONGODB_URI
        if key is None:
            logger.warning("Chat history logger has no key")
            return
        if not mock:
            try:
                client = global_mongo_client
                db = client["llm"]
                self.chat_collection = db["chat_history"]
                self.ticket_collection = db["tickets"]
                # For 'username' index on ticket_collection
                self.ticket_collection.index_information()
                self.ticket_collection.create_index("username")

                # For 'expiration' index on chat_collection
                self.chat_collection.index_information()
                self.chat_collection.create_index(
                    "expiration", expireAfterSeconds=2419200
                )
                self.expiration = datetime.utcnow() + timedelta(days=1)
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.warning("Chat history could not connect to MongoDB")
                logger.warning(e)

    def _add_chat(self, additional_data):
        if self.chat_collection is None:
            logger.error("Chat collection is not initialized")
            return
        document = {
            **self.data,
            **additional_data,
            "expiration": self.expiration,
            "index": self.index,
        }
        self.index += 1
        self.chat_collection.insert_one(document)

    def add_chat(self, additional_data):
        thread = Thread(target=self._add_chat, args=(additional_data,))
        thread.start()

    def _add_successful_ticket(self, gpt3=False):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return

        username = self.data.get("assignee", self.data["username"])
        update_fields = {self.current_month: 1, self.current_date: 1}

        if gpt3:
            key = f"{self.current_month}_gpt3"
            update_fields = {key: 1}

        self.ticket_collection.update_one(
            {"username": username}, {"$inc": update_fields}, upsert=True
        )

        ticket_count = self.get_ticket_count()
        should_decrement = (self.is_paying_user() and ticket_count >= 500) or (
            self.is_consumer_tier() and ticket_count >= 20
        )

        if should_decrement:
            self.ticket_collection.update_one(
                {"username": username}, {"$inc": {"purchased_tickets": -1}}, upsert=True
            )

        logger.info(f"Added Successful Ticket for {username}")

    def add_successful_ticket(self, gpt3=False):
        thread = Thread(target=self._add_successful_ticket, args=(gpt3,))
        thread.start()

    def _cache_key(self, username, field, metadata=""):
        return f"{username}_{field}_{metadata}"

    def get_ticket_count(
        self, use_date: bool = False, gpt3: bool = False, purchased: bool = False
    ) -> int:
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return
        username = self.data["username"]
        cache_key = self._cache_key(
            username, "ticket_count", f"{use_date}_{gpt3}_{purchased}"
        )

        if cache_key in self._ticket_count_cache:
            return self._ticket_count_cache[cache_key]
        tracking_date = self.current_date if use_date else self.current_month
        if gpt3:
            tracking_date = f"{self.current_month}_gpt3"
        query = {"username": username}
        result = self.ticket_collection.find_one(query, {tracking_date: 1, "_id": 0})
        if purchased:
            ticket_count = result.get("purchased_tickets", 0) if result else 0
        else:
            ticket_count = result.get(tracking_date, 0) if result else 0
        self._ticket_count_cache[cache_key] = ticket_count
        return ticket_count

    def _get_user_field(self, field: str):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return None

        username = self.data["username"]
        cache_key = self._cache_key(username, field)

        if cache_key in self._user_field_cache:
            return self._user_field_cache[cache_key]

        result = self.ticket_collection.find_one({"username": username}, {field: 1})

        user_field_value = result.get(field, False) if result else False
        self._user_field_cache[cache_key] = user_field_value

        return user_field_value

    def is_consumer_tier(self):
        return self._get_user_field("is_trial_user")

    def is_paying_user(self):
        return self._get_user_field("is_paying_user")

    def use_faster_model(self):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return True
        purchased_tickets = self.get_ticket_count(purchased=True)
        if self.is_paying_user():
            return self.get_ticket_count() >= 500 and purchased_tickets == 0
        if self.is_consumer_tier():
            return self.get_ticket_count() >= 20 and purchased_tickets == 0
        return (
            (self.get_ticket_count() >= 5 or self.get_ticket_count(use_date=True) > 3)
            and purchased_tickets == 0
        ) or not self.active


def discord_log_error(content, priority=0):
    """
    priority: 0 (high), 1 (medium), 2 (low)
    """
    if GITHUB_BOT_USERNAME != "sweep-ai[bot]":  # disable for dev
        return
    try:
        url = DISCORD_WEBHOOK_URL
        if priority == 1:
            url = DISCORD_MEDIUM_PRIORITY_URL
        if priority == 2:
            url = DISCORD_LOW_PRIORITY_URL

        data = {"content": content}
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, data=json.dumps(data), headers=headers)
        # Success: response.status_code == 204:
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(f"Could not log to Discord: {e}")


if __name__ == "__main__":
    chat_logger = ChatLogger(
        {
            "username": "kevinlu1248",
        }
    )
    print(chat_logger.get_ticket_count())
