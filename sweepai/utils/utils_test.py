import pytest

from sweepai.utils.code_validators import check_syntax


@pytest.mark.parametrize(
    "file_path, code, expected_validity, expected_message",
    [
        ("file.tsx", "let x = 1;", True, ""),
        ("file.tsx", "let x = ;", False, "Invalid syntax found within or before the lines 0-0, displayed below:\nlet x = ;"),
        ("file.py", "x = 1", True, ""),
    ],
)
def test_check_syntax(file_path, code, expected_validity, expected_message):
    validity, message = check_syntax(file_path, code)
    assert validity == expected_validity
    assert message == expected_message
