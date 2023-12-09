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
            "analysis_and_identification": {
                "type": "string",
                "description": "Identify that need to be made to the file. Be sure to consider all imports that are required to complete the task. Then, in a list, identify all code sections that should receive these changes and all locations code should be added.",
            },
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
                            "description": "The old lines of code that belongs to section with ID section_id. Be sure to add lines before and after to disambiguate the change.",
                        },
                        "new_code": {
                            "type": "string",
                            "description": "The new code to replace the old code.",
                        },
                    },
                    "required": ["section_id", "old_code", "new_code"],
                },
            },
        },
        "required": ["analysis_and_identification", "replaces_to_make"],
    },
    "description": "Make edits to the code file.",
}
