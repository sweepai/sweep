import os
from datetime import datetime, timedelta
from typing import Any

from pymongo import MongoClient
from pydantic import BaseModel, Field
from loguru import logger

class ChatLogger(BaseModel):
    data: dict = Field(default_factory=dict)
    chat_collection: Any = None
    expiration: datetime = None
    index: int = 0

    def __init__(self, data: dict = Field(default_factory=dict)):
        super().__init__(data=data)  # Call the BaseModel's __init__ method
        key = os.environ.get('MONGODB_URI')
        if key is None:
            logger.warning('Chat history logger has no key')
            return
        try:
            client = MongoClient(key)
            db = client['llm']
            self.chat_collection = db['chat_history']
            self.chat_collection.create_index('expireAt', expireAfterSeconds=0)
            self.expiration = datetime.utcnow() + timedelta(days=1)
        except Exception as e:
            logger.warning('Chat history could not connect to MongoDB')
            logger.warning(e)

    def get_chat_history(self):
        return self.chat_collection.find()

    def add_chat(self, additional_data):
        document = {**self.data, **additional_data, 'expiration': self.expiration, 'index': self.index}
        self.index += 1
        self.chat_collection.insert_one(document)
