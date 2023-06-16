from loguru import logger
from src.core.models import Function

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
                            "description": "The line number where the change should start. This is inclusive."
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
        start_line = int(edit['start_line'])
        end_line = int(edit['end_line'])
        new_code = edit['new_code'].split('\n')
        if new_code[-1] == '```':
            new_code[-1] = ''
        modifications.append((start_line, end_line, new_code))

    # Sort modifications by start line in reverse order
    modifications.sort(key=lambda x: x[0], reverse=True)
    lines = file_contents.split('\n')
    for start_line, end_line, new_code in modifications:
        start_formatted = False # Don't modify the start line if it's already formatted
        end_formatted = False # Don't modify the end line if it's already formatted
        if (start_line > 1 and len(new_code) > 1 
            and new_code[0:2] == lines[start_line - 2:start_line]):
            new_code = new_code[2:]
            start_formatted = True
        if (end_line + 1 < len(lines) and len(new_code) > 1 
            and new_code[-2:] == lines[end_line:end_line + 2]):
            new_code = new_code[:-2]
            end_formatted = True
        # Handle duplicate lines between the existing code and new code
        if start_line > 0 and new_code[0] == lines[start_line-1] and not start_formatted:
            new_code = new_code[1:]
        if end_line < len(lines) and new_code[-1] == lines[end_line] and not end_formatted:
            new_code = new_code[:-1]
        lines[start_line:end_line] = new_code
    return '\n'.join(lines)
