from sweepai.core.entities import FileChangeRequest
from sweepai.core.sweep_bot import ModifyBot
from tests.test_naive_chunker import file_contents

modify_bot = ModifyBot()
result = modify_bot.update_file(
    "sweepai/api.py",
    file_contents,
    FileChangeRequest(
        filename="sweepai/api.py",
        instructions="Add docstrings to all functions",
        change_type="modify",
    ),
)

print(result)
