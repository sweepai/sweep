import re

def validate_branch_name(branch_name):
    # Replace any characters that are not alphanumeric or '-' or '_' with '_'
    valid_branch_name = re.sub('[^0-9a-zA-Z_-]', '_', branch_name)
    return valid_branch_name
