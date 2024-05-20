import functools

def majority_vote_decorator(num_samples, voting_func):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            outcomes = []
            for i in range(num_samples):
                # Set the seed for each iteration
                kwargs['seed'] = i
                outcome = func(*args, **kwargs)
                outcomes.append(outcome)
            # Apply the voting function to the outcomes
            majority_outcome = voting_func(outcomes)
            return majority_outcome
        return wrapper
    return decorator