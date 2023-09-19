import os
import pickle
import hashlib

MAX_DEPTH = 3


def recursive_hash(value, depth=0):
    """Hash primitives recursively with maximum depth."""

    if depth > MAX_DEPTH:
        print("Max depth reached")
        return hashlib.md5('max_depth_reached'.encode()).hexdigest()

    if isinstance(value, (int, float, str, bool, bytes)):
        return hashlib.md5(str(value).encode()).hexdigest()
    elif isinstance(value, (list, tuple)):
        return hashlib.md5(''.join([recursive_hash(item, depth + 1) for item in value]).encode()).hexdigest()
    elif isinstance(value, dict):
        return hashlib.md5(''.join([recursive_hash(key, depth + 1) + recursive_hash(val, depth + 1) for key, val in
                                    value.items()]).encode()).hexdigest()
    elif hasattr(value, '__dict__'):
        # If it's a class instance, return a hash based on its attributes
        print(value.__dict__)
        return recursive_hash(value.__dict__, depth + 1)
    else:
        # If it's not a primitive, recognized type, or class instance, return a default hash
        return hashlib.md5('unknown'.encode()).hexdigest()


def file_cache(func):
    """Decorator to cache function output based on its inputs."""
    def wrapper(*args, **kwargs):
        cache_dir = "cache"
        os.makedirs(cache_dir, exist_ok=True)

        # Create hash based on function name and input arguments
        arg_hash = recursive_hash(args) + recursive_hash(kwargs)
        cache_file = os.path.join(cache_dir, f"{func.__module__}_{func.__name__}_{arg_hash}.pickle")

        # If cache exists, load and return it
        if os.path.exists(cache_file):
            print("Used cache for function:" + func.__name__)
            with open(cache_file, 'rb') as f:
                return pickle.load(f)

        # Otherwise, call the function and save its result to the cache
        result = func(*args, **kwargs)
        with open(cache_file, 'wb') as f:
            pickle.dump(result, f)

        return result

    return wrapper


if __name__ == "__main__":
    class state:
        def __init__(self, state):
            self.state = state

    @file_cache
    def example_function(self, a, b):
        return a + b + self.state

    self = state(0)
    print(example_function(self, 1, 3))
    self.state = 4
    print(example_function(self, 1, 4))
    self.state = 3
    print(example_function(self, 1, 4))
