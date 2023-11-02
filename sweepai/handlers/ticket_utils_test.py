import unittest
from unittest.mock import Mock
from sweepai.handlers.ticket_utils import check_if_paying_user_and_set_model, update_model_and_ticket_count_for_fast_mode, generate_payment_related_messages, generate_comment_header_with_payment_info, create_first_comment_with_payment_info

class TestTicketUtils(unittest.TestCase):
    def test_check_if_paying_user_and_set_model(self):
        chat_logger = Mock()
        g = Mock()
        is_paying_user, is_consumer_tier = check_if_paying_user_and_set_model(chat_logger, g)
        self.assertTrue(isinstance(is_paying_user, bool))
        self.assertTrue(isinstance(is_consumer_tier, bool))

    def test_update_model_and_ticket_count_for_fast_mode(self):
        fast_mode = True
        comment_id = None
        edited = False
        chat_logger = Mock()
        sandbox_mode = False
        use_faster_model = update_model_and_ticket_count_for_fast_mode(fast_mode, comment_id, edited, chat_logger, sandbox_mode)
        self.assertTrue(isinstance(use_faster_model, bool))

    def test_generate_payment_related_messages(self):
        is_paying_user = True
        is_consumer_tier = False
        daily_ticket_count = 10
        ticket_count = 100
        model_name = "GPT-4"
        payment_message_start = generate_payment_related_messages(is_paying_user, is_consumer_tier, daily_ticket_count, ticket_count, model_name)
        self.assertTrue(isinstance(payment_message_start, str))

    def test_generate_comment_header_with_payment_info(self):
        progress_headers = ["Step 1", "Step 2", "Step 3"]
        payment_message_start = "Payment message"
        config_pr_url = "https://github.com/sweepai/sweep/pull/1"
        markdown_badge = "Markdown badge"
        get_comment_header = generate_comment_header_with_payment_info(progress_headers, payment_message_start, config_pr_url, markdown_badge)
        self.assertTrue(callable(get_comment_header))

    def test_create_first_comment_with_payment_info(self):
        get_comment_header = Mock()
        progress_headers = ["Step 1", "Step 2", "Step 3"]
        indexing_message = "Indexing message"
        issue_comment = Mock()
        current_issue = Mock()
        create_first_comment_with_payment_info(get_comment_header, progress_headers, indexing_message, issue_comment, current_issue)
        issue_comment.create_comment.assert_called_once()
        issue_comment.edit.assert_called_once()

if __name__ == "__main__":
    unittest.main()
