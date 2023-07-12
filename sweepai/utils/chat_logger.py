import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import requests
from loguru import logger
from pydantic import BaseModel, Field
from pymongo import MongoClient

from sweepai.utils.config.server import MONGODB_URI, DISCORD_WEBHOOK_URL


class ChatLogger(BaseModel):
    data: dict = Field(default_factory=dict)
    chat_collection: Any = None
    ticket_collection: Any = None
    expiration: datetime = None
    index: int = 0
    current_month: str = datetime.utcnow().strftime('%m/%Y')

    def __init__(self, data: dict = Field(default_factory=dict)):
        super().__init__(data=data)  # Call the BaseModel's __init__ method
        key = MONGODB_URI
        if key is None:
            logger.warning('Chat history logger has no key')
            return
        try:
            client = MongoClient(key, serverSelectionTimeoutMS=5000, socketTimeoutMS=5000)
            db = client['llm']
            self.chat_collection = db['chat_history']
            self.ticket_collection = db['tickets']
            self.ticket_collection.create_index('username')
            self.chat_collection.create_index('expireAt', expireAfterSeconds=0)
            self.expiration = datetime.utcnow() + timedelta(days=1)
        except Exception as e:
            logger.warning('Chat history could not connect to MongoDB')
            logger.warning(e)

    def get_chat_history(self, filters):
        return self.chat_collection.find(filters) \
            .sort([('expiration', 1), ('index', 1)]) \
            .limit(2000)

    def add_chat(self, additional_data):
        document = {**self.data, **additional_data, 'expiration': self.expiration, 'index': self.index}
        self.index += 1
        self.chat_collection.insert_one(document)

    def add_successful_ticket(self):
        if self.ticket_collection is None:
            logger.error('Ticket Collection Does Not Exist')
            return
        username = self.data['username']
        self.ticket_collection.update_one(
            {'username': username},
            {'$inc': {self.current_month: 1}},
            upsert=True
        )
        logger.info(f'Added Successful Ticket for {username}')

    def get_ticket_count(self):
        if self.ticket_collection is None:
            logger.error('Ticket Collection Does Not Exist')
            return 0
        username = self.data['username']
        result = self.ticket_collection.aggregate([
            {'$match': {'username': username}},
            {'$project': {self.current_month: 1, '_id': 0}}
        ])
        result_list = list(result)
        ticket_count = result_list[0].get(self.current_month, 0) if len(result_list) > 0 else 0
        logger.info(f'Ticket Count for {username} {ticket_count}')
        return ticket_count

    def is_paying_user(self):
        if self.ticket_collection is None:
            logger.error('Ticket Collection Does Not Exist')
            return False
        username = self.data['username']
        result = self.ticket_collection.find_one({'username': username})
        return result.get('is_paying_user', False) if result else False

    def use_faster_model(self):
        if self.ticket_collection is None:
            logger.error('Ticket Collection Does Not Exist')
            return True
        if self.is_paying_user():
            return self.get_ticket_count() >= 60
        return self.get_ticket_count() >= 3


def discord_log_error(content):
    try:
        url = DISCORD_WEBHOOK_URL
        data = {'content': content}
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data=json.dumps(data), headers=headers)
        # Success: response.status_code == 204:
    except Exception as e:
        logger.error(f'Could not log to Discord: {e}')
        pass
