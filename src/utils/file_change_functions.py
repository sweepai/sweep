from loguru import logger
from src.core.chat import Function
from src.utils.diff import format_contents

modify_file_function = Function(
    name="modify_file",
    description="Edits the code in a file. Be sure to properly indent and format the code in `new_code`. Output the code in the order it should appear in the file. Make sure `start_line` and `end_line` do not overlap between code edits.",
    parameters={
        "type": "object",
        "properties": {
            "file_name": {
                "type": "string",
                "description": "The name of the file to modify."
            },
            "code_edits": {
                "type": "array",
                "items": {
                    "type": "object",
"properties": {
                        "start_line": {
                            "type": "integer",
                            "description": "The index where the change should start."
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "The index where the code should end. Add 1 to this number to include the line."
                        },
                        "old_code": {
                            "type": "string",
                            "description": "The code to replace. Format this code with the same indents, brackets as it appears in the file."
                        },
                        "new_code": {
                            "type": "string",
                            "description": "The code to insert into the file. Format this code keeping in mind indentation. If you want to delete a line, set this to '' (single quoted empty string)."
                        },
                        "indentation": {
                            "type": "integer",
                            "description": "The number of tabs to indent."
                        }
                    },
                    "required": ["start_line", "end_line", "old_code", "new_code"]
                },
                "description": "An array of edits. Each `code_edit` represents a span delimited by `start_line` and `end_line`. Both `start_line` and `end_line` are zero-indexed and inclusive."
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
        new_code = format_contents(edit['new_code'])
        # Starts with or ends with "" should be swapped to '' for json
        if len(new_code) >= 2 and new_code[:1] == '""':
            new_code = "''" + new_code[2:]
        elif len(new_code) >= 2 and new_code[-2:] == '""':
            new_code = new_code[:-2] + "''"
new_code = [\t*edit['indentation'] + line for line in edit['new_code'].split('\n')]
        modifications.append((start_line, end_line, new_code))

    # Sort modifications by start line in reverse order
    modifications.sort(key=lambda x: x[0], reverse=True)
    lines = file_contents.split('\n')
    for start_line, end_line, new_code in modifications:
        if start_line > end_line:
            logger.error(f"Start line {start_line} is greater than end line {end_line}")
            continue
        if start_line < 0:
            logger.error(f"Start line {start_line} is less than 0")
            continue
        if end_line > len(lines) - 1:
            logger.error(f"End line {end_line} is greater than the number of lines in the file {len(lines)}")
            continue
        # Handle duplicate lines between the existing code and new code
        if start_line > 0 and end_line < len(lines) \
            and new_code[0] == lines[start_line-1] and new_code[-1] == lines[end_line]:
            new_code = new_code[1:-1]
            lines[start_line:end_line] = new_code
            continue
        elif start_line > 0 and new_code[0] == lines[start_line-1]:
            new_code = new_code[1:]
            lines[start_line-1:end_line + 1] = new_code # Exit and merge first line
            continue
        elif end_line < len(lines) and new_code[-1] == lines[end_line]:
            new_code = new_code[:-1]
            lines[start_line:end_line] = new_code # Exit and merge last line
            continue
        # Check index error
        if end_line > len(lines) - 1:
            end_line = len(lines) - 1
        lines[start_line:end_line + 1] = new_code # Start and end are inclusive
    return '\n'.join(lines)