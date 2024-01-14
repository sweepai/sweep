import unittest
from unittest.mock import patch
from sweepai.handlers import on_comment

class TestOnComment(unittest.TestCase):
    @patch('sweepai.handlers.on_comment.on_comment')
    def test_on_comment(self, mock_on_comment):
        # Arrange
        mock_on_comment.return_value = '\n'.join(['line' + str(i) for i in range(20)])
        pr_line_position = 10

        # Act
        result = on_comment.on_comment(
            repo_full_name='test/repo',
            repo_description='Test repo',
            comment='Test comment',
            pr_path='test/path',
            pr_line_position=pr_line_position,
            username='test_user',
            installation_id=1,
            pr_number=1,
            comment_id=1
        )

        # Assert
        self.assertEqual(len(result.split('\n')), 20)
        self.assertEqual(result.split('\n')[10], 'line10')

if __name__ == '__main__':
    unittest.main()
