import unittest
from unittest.mock import call, patch

from sweepai.utils.chat_logger import ChatLogger


class TestChatLogger(unittest.TestCase):
    def setUp(self):
        self.base_model_patch = patch('sweepai.utils.chat_logger.BaseModel')
        self.mock_base_model = self.base_model_patch.start()

    def tearDown(self):
        self.base_model_patch.stop()

    def test_init(self):
        kwargs = {'arg1': 'value1', 'arg2': 'value2'}
        chat_logger = ChatLogger(data={}, mock=False, **kwargs)
        self.mock_base_model.assert_has_calls([call(data={}, **kwargs)])

    def test_no_regressions(self):
        chat_logger = ChatLogger(data={}, mock=False)
        self.mock_base_model.assert_has_calls([call(data={})])
