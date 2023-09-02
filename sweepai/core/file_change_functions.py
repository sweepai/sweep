import os

def check_file_size(file):
    """
    This function checks if the size of the file is greater than 60000 bytes.
    It uses os.stat() instead of reading the whole file which is more efficient.
    """
    file_info = os.stat(file)
    if file_info.st_size > 60000:
        return False
    return True
