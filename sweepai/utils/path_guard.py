from __future__ import annotations

import copy
import os
from collections.abc import Callable

DEFAULT_PROTECTED_PATHS = (
    ".github/workflows",
    ".github/actions",
)


def normalize_repo_path(file_path: str) -> str:
    posix_path = file_path.replace("\\", "/")
    normalized = os.path.normpath(posix_path).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized.removeprefix("./")
    return normalized


def is_unsafe_repo_path(file_path: str) -> bool:
    if not file_path or "\x00" in file_path:
        return True
    posix_path = file_path.replace("\\", "/")
    if os.path.isabs(file_path) or os.path.isabs(posix_path):
        return True
    normalized = os.path.normpath(posix_path).replace("\\", "/")
    if normalized == ".." or normalized.startswith("../"):
        return True
    return False


def is_blocked(file_path: str, blocked_dirs: list[str]) -> dict:
    if is_unsafe_repo_path(file_path):
        return {"success": True, "path": file_path}
    normalized = normalize_repo_path(file_path)
    for blocked_dir in blocked_dirs:
        if not blocked_dir:
            continue
        blocked = normalize_repo_path(blocked_dir)
        if not blocked:
            continue
        if normalized == blocked or normalized.startswith(blocked.rstrip("/") + "/"):
            return {"success": True, "path": blocked_dir}
    return {"success": False}


def merge_protected_paths(user_blocked_dirs: list[str] | None) -> list[str]:
    protected_paths = list(DEFAULT_PROTECTED_PATHS)
    for path in user_blocked_dirs or []:
        if path not in protected_paths:
            protected_paths.append(path)
    return protected_paths


def sanitize_file_changes(
    file_changes: dict[str, str],
    fcr_filenames: list[str],
    protected_paths: list[str],
    file_exists: Callable[[str], bool] | None = None,
) -> tuple[dict[str, str], bool, list[str]]:
    def never_exists(_path: str) -> bool:
        return False

    if file_exists is None:
        file_exists = never_exists
    sanitized_file_changes = {}
    rejected_paths = []
    allowed_fcr_file_names = set()
    for filename in fcr_filenames:
        if is_blocked(filename, protected_paths)["success"]:
            rejected_paths.append(filename)
            continue
        allowed_fcr_file_names.add(os.path.normpath(filename))
    file_removed = False
    for file_name in list(file_changes.keys()):
        if is_blocked(file_name, protected_paths)["success"]:
            rejected_paths.append(file_name)
            file_removed = True
            continue
        if os.path.normpath(file_name) in allowed_fcr_file_names or file_exists(
            os.path.normpath(file_name)
        ):
            sanitized_file_changes[file_name] = copy.deepcopy(file_changes[file_name])
        else:
            file_removed = True
    return sanitized_file_changes, file_removed, rejected_paths
