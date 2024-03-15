def safe_multiprocessing_setup(num_processes):
    return max(1, num_processes)
