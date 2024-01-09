import pytest

from sweepai.utils.utils import get_line_number, check_syntax


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


@pytest.mark.parametrize(
    "index, source_code, expected_line_number",
    [
        (0, "", 0),
        (0, "line 1\nline 2", 1),
        (0, "line 1\n\n\nline 2", 1),
        (7, "line 1\nline 2\n", 2),
        (14, "line 1\nline 2", 2),
        (15, "line 1\nline 2\n", 3),
        (16, "line 1\nline 2\n", 3),
        (17, "line 1\nline 2\n", 3),
        (25, "line 1\nline 2", 3),
        (10, "line 1\nline 2\nline 3\n", len("line 1\nline 2\nline 3\n".splitlines()))
    ],
)
def test_get_line_number(index, source_code, expected_line_number):
    line_number = get_line_number(index, source_code)
    assert line_number == expected_line_number
