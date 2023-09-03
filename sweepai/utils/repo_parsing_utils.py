import os

def check_file_size(file):
    """Check if the size of the file is less than 60000 bytes."""
    file_size = os.stat(file).st_size
    if file_size > 60000:
        return False
    return True
