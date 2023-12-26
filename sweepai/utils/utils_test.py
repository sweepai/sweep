import unittest
from unittest.mock import call, patch, Mock

from sweepai.utils.utils import check_valid_typescript


class TestDockerUtils(unittest.TestCase):
    def test_check_valid_typescript(self):
        test_code = "let x: number = 5;"

        with patch('subprocess.run', return_value=Mock(returncode=0)) as mock_run, patch('os.remove') as mock_remove:
            check_valid_typescript(test_code)

            mock_run.assert_called_once_with(['npx', 'prettier', '--parser', 'babel-ts', call.ANY], capture_output=True)
            mock_remove.assert_called_once_with(call.ANY)
