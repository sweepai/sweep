raise_error_schema = {
    "name": "raise_error",
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Message for the user describing the error, either indicating that there's an internal error or that you do not have the necessary information to complete the task. Add all potentially relevant details and use markdown for formatting.",
            }
        },
        "required": ["message"],
    },
    "description": "Use this when you absolutely cannot complete the task on your own.",
}

search_and_replace_schema = {
    "name": "search_and_replace",
    "parameters": {
        "type": "object",
        "properties": {
            "replaces_to_make": {
                "type": "array",
                "description": "Array of sections to modify",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_id": {
                            "type": "string",
                            "description": "The section ID the original code belongs to.",
                        },
                        "old_code": {
                            "type": "string",
                            "description": "The old lines of code that belongs to section with ID section_id.",
                        },
                        "new_code": {
                            "type": "string",
                            "description": "The new code to replace the old code.",
                        },
                    },
                },
            }
        },
        "required": ["replaces_to_make"],
    },
    "description": "Make edits to the code file.",
}
