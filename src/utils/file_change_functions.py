from loguru import logger
from src.core.chat import Function

modify_file_function = Function(
    name="modify_file",
    description="Edits a file with code. Be sure to properly indent and format the code in `new_code`. Also make sure start_line is in ascending order and that the code_edits do not overlap.",
    parameters={
        "type": "object",
        "properties": {
            "file_name": {
                "type": "string",
                "description": "The name of the file to modify or create."
            },
            "code_edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_line": {
                            "type": "integer",
                            "description": "The line number where the change should start."
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "The line number where the change should end. This is inclusive."
                        },
                        "old_code": {
                            "type": "string",
                            "description": "The code to replace. Format this code with the same indents, brackets, etc."
                        },
                        "new_code": {
                            "type": "string",
                            "description": "The code to insert into the file. Format this code to match old_code."
                        }
                    },
                    "required": ["start_line", "end_line", "old_code", "new_code"]
                },
                "description": "An array of edits. Each edit consists of a start_line, end_line, the old code, and the code to replace."
            }
        },
        "required": ["file_name", "code_edits"]
        }

)

def apply_code_edits(file_contents, code_edits):
    modifications = []
    for edit in code_edits:
        logger.info(f"Edit: {edit}")
        start_line = int(edit['start_line'])
        end_line = int(edit['end_line'])
        new_code = edit['new_code'].split('\n')
        modifications.append((start_line, end_line, new_code))

    # Sort modifications by start line in reverse order
    modifications.sort(key=lambda x: x[0], reverse=True)
    lines = file_contents.split('\n')
    for start_line, end_line, new_code in modifications:
        lines[start_line:end_line] = new_code
    return '\n'.join(lines)