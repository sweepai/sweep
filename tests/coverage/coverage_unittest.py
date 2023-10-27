import re



# Using regex to parse the coverage data
coverage_lines = coverage_data.strip().split('\n')[2:-2]  # Skip header and total lines
coverage_info = {}

for line in coverage_lines:
    match = re.match(r'(.+?)\s+(\d+)\s+(\d+)\s+(\d+%)', line)
    if match:
        file_name, _, _, coverage_percent = match.groups()
        if "__init__.py" not in file_name:
            coverage_info[file_name.strip()] = coverage_percent

coverage_info