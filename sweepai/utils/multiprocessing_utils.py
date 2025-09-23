import logging


def get_safe_process_count(requested_processes: int = 1) -> int:
    if requested_processes < 1:
        logging.warning("Requested process count is less than 1. Adjusting to 1 to ensure stability.")
        return 1
    return requested_processes
