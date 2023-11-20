from pydantic import BaseModel

from sweepai.utils.str_utils import create_collapsible, inline_code


class FileSummary(BaseModel):
    covered_lines: int
    num_statements: int
    percent_covered: float
    percent_covered_display: str
    missing_lines: int
    excluded_lines: int


class FileDetail(BaseModel):
    executed_lines: list[int]
    summary: FileSummary
    missing_lines: list[int]
    excluded_lines: list[int]


class CoverageMeta(BaseModel):
    version: str
    timestamp: str
    branch_coverage: bool
    show_contexts: bool


# class CoverageData(BaseModel):
#     meta: CoverageMeta
#     files: dict[str, FileDetail]
#     totals: FileSummary


class CoverageData(BaseModel):
    meta: dict
    files: dict[str, FileDetail]


def render_coverage_data(coverage_data, project_dir="."):
    coverage_data = CoverageData(**coverage_data)
    version = coverage_data.meta["version"]
    result = f"#### Test coverage (via coverage.py `v{version}`):\n"
    for file_path, file_detail in coverage_data.files.items():
        if file_path == "total":
            continue
        file_contents = open(project_dir + "/" + file_path).readlines()
        mode = " "
        for i, line in enumerate(file_contents):
            if i + 1 in file_detail.missing_lines:
                mode = "-"
            elif i + 1 in file_detail.excluded_lines:
                mode = "?"
            elif i + 1 in file_detail.executed_lines:
                mode = "+"
            file_contents[i] = f"{mode} {line}"
        file_contents = "".join(file_contents)
        file_contents = create_collapsible(
            f"{inline_code(file_path)} ({file_detail.summary.percent_covered_display}%)",
            f"```diff\n{file_contents}\n```",
            opened=True,
        )
        result += file_contents
    return result


if __name__ == "__main__":
    coverage_data = {
        "meta": {
            "version": "7.3.2",
            "timestamp": "2023-11-18T16:15:43.877037",
            "branch_coverage": False,
            "show_contexts": False,
        },
        "files": {
            "sweepai/agents/complete_code.py": {
                "executed_lines": [
                    1,
                    5,
                    7,
                    9,
                    10,
                    11,
                    13,
                    17,
                    35,
                    36,
                    38,
                    39,
                    56,
                    57,
                    58,
                    59,
                    60,
                    61,
                    64,
                    69,
                    70,
                    78,
                ],
                "summary": {
                    "covered_lines": 21,
                    "num_statements": 37,
                    "percent_covered": 56.75675675675676,
                    "percent_covered_display": "57",
                    "missing_lines": 16,
                    "excluded_lines": 0,
                },
                "missing_lines": [
                    40,
                    41,
                    44,
                    47,
                    48,
                    49,
                    50,
                    51,
                    71,
                    72,
                    73,
                    74,
                    75,
                    79,
                    85,
                    86,
                ],
                "excluded_lines": [],
            }
        },
        "totals": {
            "covered_lines": 21,
            "num_statements": 37,
            "percent_covered": 56.75675675675676,
            "percent_covered_display": "57",
            "missing_lines": 16,
            "excluded_lines": 0,
        },
    }
    print(render_coverage_data(coverage_data))
