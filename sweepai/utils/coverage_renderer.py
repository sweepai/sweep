from pydantic import BaseModel


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


class CoverageData(BaseModel):
    meta: CoverageMeta
    files: dict[str, FileDetail]
    totals: FileSummary


class CoverageData(BaseModel):
    meta: dict
    files: dict[str, FileDetail]


def parse_coverage_data_to_table(coverage_data, project_dir="."):
    coverage_data = CoverageData(**coverage_data)
    result = ""
    for file_path, file_detail in coverage_data.files.items():
        if file_path == "total":
            continue
        file_contents = open(project_dir + "/" + file_path).readlines()
        for i, line in enumerate(file_contents):
            if i + 1 in file_detail.missing_lines:
                file_contents[i] = f"? {line}"
            elif i + 1 in file_detail.excluded_lines:
                file_contents[i] = f"? {line}"
            elif i + 1 in file_detail.executed_lines:
                file_contents[i] = f"+ {line}"
            else:
                file_contents[i] = f"  {line}"
        file_contents = "".join(file_contents)
        result += f"\nTest coverage for {file_path}\n```diff\n{file_contents}\n```\n"
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
    print(parse_coverage_data_to_table(coverage_data))
