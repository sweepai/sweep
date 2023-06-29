from collections import Counter

def majority_vote(query_results):
    """
    Takes a list of lists as input (each sub-list contains the result files for a query)
    and returns a list of result files that appear most frequently across all queries.
    """
    # Create a Counter object to count the frequency of each result file
    result_counter = Counter()

    # Iterate over each query's result files and update the counter
    for results in query_results:
        result_counter.update(results)

    # Find the maximum frequency
    max_freq = max(result_counter.values())

    # Return the result files with the maximum frequency
    return [file for file, freq in result_counter.items() if freq == max_freq]
