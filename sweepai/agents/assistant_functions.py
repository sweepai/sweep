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
                "description": "The keyword to search for.",
            },
        },
        "required": ["justification", "keyword"],
    },
    "description": "Searches for all lines in the file containing the keyword. The file is already loaded and does not need to specified.",
    "returns": {
        "type": "object",
        "properties": {
            "section_ids": {
            "type": "array",
            "description": "Section IDs from the file that contain the keyword.",
                "items": {
                    "type": "string",
                    "description": "The section ID in which the keyword was found.",
                },
            },
            "sections": {
                "type": "array",
                "description": "Sections, including ID and actual code with pointers to matches, from the file that contain the keyword.",
                "items": {
                    "type": "string",
                    "description": "The entire code of the section in which the keyword was found, e.g. <section id=AA> (2 matches)\n# ... code with matches\n</section>",
                },
            }
        },
    }
}

search_and_replace_schema = {
    "name": "search_and_replace",
    "parameters": {
        "type": "object",
        "properties": {
            "analysis_and_identification": {
                "type": "string",
                "description": "Identify and list the minimal changes that need to be made to the file by listing all code section IDs that should receive these changes and the intended changes to be made. A developer will review all requested sections and perform edits on them based on your instructions in `task`.",
            },
            "task": {
                "type": "string",
                "description": "The overall task to accomplish by writing changes applied to the code sections.",
            },
            "section_ids": {
                "type": "array",
                "description": "Relevant section IDs from keyword_search results whose code to read.",
                "items": {
                    "type": "string",
                    "description": "The section ID the original code belongs to.",
                },
            },
        },
        "required": ["analysis_and_identification", "task", "section_ids"],
    },
    "description": "MUST RUN AFTER keyword_search. Given a task, read multiple relevant code sections (AS RETURNED BY keyword_search) and suggest edits.",
    "returns": {
        "type": "object",
        "properties": {
            "success_message": {
                "type": "string",
                "description": "Success message including the full diff after making edits to the code sections.",
            },
            "error": {
                "type": "string",
                "description": "Error message and explanation if the task was not successful.",
            },
        },
    }
}
