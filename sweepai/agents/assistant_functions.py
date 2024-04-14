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

chain_of_thought_schema = {
    "name": "propose_problem_analysis_and_plan",
    "parameters": {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "string",
                "description": "Break down the problem and identify important pieces of information that will be needed to solve the problem, such as the relevant keywords, the intended behavior, and the required imports.",
            },
            "plan": {
                "type": "string",
                "description": "Describe the plan for the task, including the keywords to search and the modifications to make. Be sure to consider all imports that are required to complete the task.",
            },
        },
        "required": ["analysis", "plan"],
    },
}

search_and_replace_schema = {
    "name": "search_and_replace",
    "parameters": {
        "type": "object",
        "properties": {
            "analysis_and_identification": {
                "type": "string",
                "description": "Identify and list the minimal changes that need to be made to the file, by listing all locations that should receive these changes and the changes to be made. Be sure to consider all imports that are required to complete the task.",
            },
            "replaces_to_make": {
                "type": "array",
                "description": "Array of sections of code to modify.",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_id": {
                            "type": "string",
                            "description": "The section ID the original code belongs to.",
                        },
                        "old_code": {
                            "type": "string",
                            "description": "The old lines of code. Be sure to add lines before and after to disambiguate the change.",
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

view_sections_schema = {
    "name": "view_sections",
    "parameters": {
        "type": "object",
        "properties": {
            "section_ids": {
                "type": "array",
                "description": "Section IDs to view",
                "items": {
                    "type": "string",
                    "description": "The section ID to view.",
                },
            },
        },
        "required": ["section_ids"],
    },
    "description": "Searches for sections in the file and returns the code for each section.",
}

keyword_search_schema = {
    "name": "keyword_search",
    "parameters": {
        "type": "object",
        "properties": {
            "justification": {
                "type": "string",
                "description": "Justification for searching the keyword.",
            },
            "keyword": {
                "type": "string",
                "description": "The keyword to search for. This is the keyword itself that you want to search for in the contents of the file, not the name of the file itself.",
            },
        },
        "required": ["justification", "keyword"],
    },
    "description": "Searches for all lines in the file containing the keyword.",
}

submit_schema = {
    "name": "submit",
    "parameters": {
        "type": "object",
        "properties": {
            "justification": {
                "type": "string",
                "description": "Justification for why you are finished with the task.",
            },
        },
        "required": ["justification"],
    },
    "description": "Indicates that you have completed the task successfully.",
}