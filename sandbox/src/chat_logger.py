import os
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, Field
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI")


class ChatLogger(BaseModel):
    data: dict
    chat_collection: Any = None
    ticket_collection: Any = None
    expiration: datetime = None
    index: int = 0
    current_date: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%m/%Y/%d")
    )
    current_month: str = Field(
        default_factory=lambda: datetime.utcnow().strftime("%m/%Y")
    )

    def __init__(self, data: dict):
        super().__init__(data=data)  # Call the BaseModel's __init__ method
        key = MONGODB_URI
        if key is None:
            logger.warning(
                "MONGODB_URI is not set. Chat history logger cannot connect to MongoDB."
            )
            return
        try:
            client = MongoClient(
                key, serverSelectionTimeoutMS=5000, socketTimeoutMS=5000
            )
            db = client["llm"]
            self.chat_collection = db["chat_history"]
            self.ticket_collection = db["tickets"]
            self.ticket_collection.create_index("username")
            self.chat_collection.create_index(
                "expiration", expireAfterSeconds=2419200
            )  # 28 days data persistence
            self.expiration = datetime.utcnow() + timedelta(
                days=1
            )  # 1 day since historical use case
        except Exception as e:
            logger.warning("Chat history could not connect to MongoDB")
            logger.warning(e)

    def get_chat_history(self, filters):
        return (
            self.chat_collection.find(filters)
            .sort([("expiration", 1), ("index", 1)])
            .limit(2000)
        )

    def add_chat(self, additional_data):
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

    def add_successful_ticket(self, gpt3=False):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return
        username = self.data["username"]
        if "assignee" in self.data:
            username = self.data["assignee"]
        if gpt3:
            key = f"{self.current_month}_gpt3"
            self.ticket_collection.update_one(
                {"username": username},
                {"$inc": {key: 1}},
                upsert=True,
            )
        else:
            self.ticket_collection.update_one(
                {"username": username},
                {"$inc": {self.current_month: 1, self.current_date: 1}},
                upsert=True,
            )
        logger.info(f"Added Successful Ticket for {username}")

    def get_ticket_count(self, use_date=False, gpt3=False):
        # gpt3 overrides use_date
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return 0
        username = self.data["username"]
        tracking_date = self.current_date if use_date else self.current_month
        if gpt3:
            tracking_date = f"{self.current_month}_gpt3"
        result = self.ticket_collection.aggregate(
            [
                {"$match": {"username": username}},
                {"$project": {tracking_date: 1, "_id": 0}},
            ]
        )
        result_list = list(result)
        ticket_count = (
            result_list[0].get(tracking_date, 0) if len(result_list) > 0 else 0
        )
        logger.info(f"Ticket Count for {username} {ticket_count}")
        return ticket_count

    def is_paying_user(self):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return False
        username = self.data["username"]
        result = self.ticket_collection.find_one({"username": username})
        return result.get("is_paying_user", False) if result else False

    def is_consumer_tier(self):
        """
        Check if the user is a consumer tier user.
        """
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return False
        username = self.data["username"]
        result = self.ticket_collection.find_one({"username": username})
        return result.get("is_trial_user", False) if result else False

    def use_faster_model(self, g):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return True
        if self.is_paying_user():
            return self.get_ticket_count() >= 500
        if self.is_consumer_tier():
            return self.get_ticket_count() >= 20
        return self.get_ticket_count() >= 5 or self.get_ticket_count(use_date=True) > 3
