def ensure_min_processes(num_processes: int) -> int:
    return max(1, num_processes)
