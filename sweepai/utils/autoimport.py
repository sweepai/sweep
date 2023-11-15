"""
Auto imports for Python code.
"""

import os
from io import StringIO

import isort
from importmagic import index
from loguru import logger
from pyflakes.api import check
from pyflakes.reporter import Reporter

from sweepai.utils.chat_logger import discord_log_error


def get_module_of_entity(
    entity_name: str,
    project_name: str,
) -> str | None:
    my_index = index.SymbolIndex()
    my_index.build_index([project_name])
    results = my_index.symbol_scores(entity_name)
    if results:
        return results[0][1]
    return None


def get_undefined_names(code: str, file_path: str) -> list[str]:
    output = StringIO()
    reporter = Reporter(output, output)
    check(code, filename=file_path, reporter=reporter)
    undefined_names = []
    for line in output.getvalue().splitlines():
        if "undefined name" in line:
            entity = line.split()[-1].strip("'")
            if entity not in undefined_names:
                undefined_names.append(entity)
    return undefined_names


def add_auto_imports(
    file_path: str,
    project_name: str,
    code: str | None = None,
    run_isort: bool = True,
):
    code = open(os.path.join(project_name, file_path)).read() if code is None else code
    if not file_path.endswith(".py"):
        return code
    try:
        undefined_names = get_undefined_names(code, file_path)
        for undefined_name in undefined_names:
            module = get_module_of_entity(undefined_name, project_name)
            if module:
                code = f"from {module} import {undefined_name}\n{code}"
        if run_isort:
            code = isort.code(code)
        return code
    except Exception as e:
        logger.exception(e)
        discord_log_error(e)
        return code


if __name__ == "__main__":
    code = """
def hello():
    print(undeclared_var)
"""
    # print(get_undefined_names(code, "example.py"))
    print(add_auto_imports("sweepai/core/repo_parsing_utils.py", "/home/kevin/sweep"))
