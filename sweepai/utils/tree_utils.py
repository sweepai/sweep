import copy
from logn import logger
from collections import OrderedDict

class Line:
    def __init__(self, indent_count, text, parent=None, is_dir=False):
        self.indent_count = indent_count
        self.text = text
        self.parent = parent
        self.is_dir = is_dir

    def full_path(self):
        return self.text if not self.is_dir else self.text
    
    def __eq__(self, other):
        return self.full_path() == other.full_path()
    
    def __str__(self):
        return self.full_path()
    
    def __repr__(self):
        return self.full_path()

class DirectoryTree:
    def __init__(self):
        self.original_lines = []
        self.lines = []

    def parse(self, input_str):
        stack = []  # To keep track of parent directories
        for line in input_str.strip().split("\n"):
            indent_count = (len(line) - len(line.lstrip())) // 2
            line = line.strip()

            # Pop items from stack to find the correct parent directory
            while stack and stack[-1].indent_count >= indent_count:
                stack.pop()

            is_directory = line.endswith("/") or line.endswith("...")
            parent = stack[-1] if stack else None
            line_obj = Line(indent_count, line, parent, is_dir=is_directory)

            if line.endswith("/"):
                stack.append(line_obj)

            self.lines.append(line_obj)
        self.original_lines = copy.deepcopy(self.lines)

    def remove(self, target):
        new_lines = []
        skip_until_indent = None
        for line in self.lines:
            if line.full_path() == target:
                skip_until_indent = line.indent_count
                continue

            if skip_until_indent is not None and line.indent_count > skip_until_indent:
                logger.print("Skipping:", line.full_path())
                continue

            skip_until_indent = None
            new_lines.append(line)

        self.lines = new_lines

    def remove_all_not_included(self, included):
        new_lines = []
        for line in self.lines:
            if line.is_dir:
                full_relative_path = line.full_path()
            else:
                full_relative_path = line.parent.full_path() + line.full_path() if line.parent else line.full_path()
            if any(included_path.startswith(full_relative_path) for included_path in included):
                parent_list = []
                curr_parent = line.parent
                while curr_parent and curr_parent not in new_lines:
                    parent_list.append(line.parent)
                    curr_parent = curr_parent.parent
                new_lines.extend(parent_list[::-1])
                new_lines.append(line)
            elif line.parent and line.parent.full_path() in included:
                new_lines.append(line)
        self.lines = new_lines

    def expand_directory(self, dirs_to_expand):
        expanded_lines = []
        for line in self.original_lines:
            # In current lines or should be expanded
            full_relative_path = line.parent.full_path() + line.full_path() if line.parent else line.full_path()
            if any(full_relative_path.startswith(dir) for dir in dirs_to_expand):
                expanded_lines.append(line)
            elif line in self.lines:
                expanded_lines.append(line)
        self.lines = expanded_lines

    def remove_multiple(self, targets):
        for target in targets:
            self.remove(target)

    def __str__(self):
        return "\n".join(
            ("  " * line.indent_count) + line.full_path() for line in self.lines
        )
