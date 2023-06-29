import collections

def majority_vote(result_files):
    """
    Takes a list of result files from each query and returns the most common result files.
    
    Args:
        result_files (list): A list of result files from each query.
        
    Returns:
        list: The most common result files.
    """
    file_counts = collections.Counter(result_files)
    max_count = max(file_counts.values())
    most_common_files = [file for file, count in file_counts.items() if count == max_count]
    
    return most_common_files
