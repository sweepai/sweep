import unittest
from unittest.mock import patch, MagicMock
from sweep import code_repair

class TestCodeRepairer(unittest.TestCase):
    @patch.object(code_repair.CodeRepairer, 'repair')
    def test_repair(self, mock_repair):
        cr = code_repair.CodeRepairer()
        cr.repair("code")
        mock_repair.assert_called_with("code")
</new_file>

