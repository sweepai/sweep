import os
import tempfile
import pytest

from sweepai.utils.file_change_functions import apply_code_edits

def test_apply_code_edits():
    # Create a temporary file smaller than 60000
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp.write(b'a' * 50000)
    assert apply_code_edits(temp.name) == False
    os.remove(temp.name)

    # Create a temporary file larger than 60000
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp.write(b'a' * 70000)
    assert apply_code_edits(temp.name) == True
    os.remove(temp.name)
