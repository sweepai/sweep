import hashlib
import os
import pickle
from loguru import logger
from sweepai.config.server import GITHUB_BOT_USERNAME

TEST_BOT_NAME = "sweep-nightly[bot]"
MAX_DEPTH = 6


def recursive_hash(value, depth=0, ignore_params=[]):
    """Hash primitives recursively with maximum depth."""
    if depth > MAX_DEPTH:
        return hashlib.md5("max_depth_reached".encode()).hexdigest()

    if isinstance(value, (int, float, str, bool, bytes)):
        return hashlib.md5(str(value).encode()).hexdigest()
    elif isinstance(value, (list, tuple)):
        return hashlib.md5(
            "".join(
                [recursive_hash(item, depth + 1, ignore_params) for item in value]
            ).encode()
        ).hexdigest()
    elif isinstance(value, dict):
        return hashlib.md5(
            "".join(
                [
                    recursive_hash(key, depth + 1, ignore_params)
                    + recursive_hash(val, depth + 1, ignore_params)
                    for key, val in value.items()
                    if key not in ignore_params
                ]
            ).encode()
        ).hexdigest()
    elif hasattr(value, "__dict__") and value.__class__.__name__ not in ignore_params:
        return recursive_hash(value.__dict__, depth + 1, ignore_params)
    else:
        return hashlib.md5("unknown".encode()).hexdigest()


def file_cache(ignore_params=[]):
    """Decorator to cache function output based on its inputs, ignoring specified parameters."""

    def decorator(func):
        if GITHUB_BOT_USERNAME != TEST_BOT_NAME:
            return func

        def wrapper(*args, **kwargs):
            cache_dir = "/tmp/file_cache"
            os.makedirs(cache_dir, exist_ok=True)

            # Convert args to a dictionary based on the function's signature
            args_names = func.__code__.co_varnames[: func.__code__.co_argcount]
            args_dict = dict(zip(args_names, args))

            # Remove ignored params
            kwargs_clone = kwargs.copy()
            for param in ignore_params:
                args_dict.pop(param, None)
                kwargs_clone.pop(param, None)

            # Create hash based on function name and input arguments
            arg_hash = recursive_hash(
                args_dict, ignore_params=ignore_params
            ) + recursive_hash(kwargs_clone, ignore_params=ignore_params)
            cache_file = os.path.join(
                cache_dir, f"{func.__module__}_{func.__name__}_{arg_hash}.pickle"
            )

            try:
                # If cache exists, load and return it
                if os.path.exists(cache_file):
                    print("Used cache for function: " + func.__name__)
                    with open(cache_file, "rb") as f:
                        return pickle.load(f)
            except Exception as e:
                logger.info("Unpickling failed")

            # Otherwise, call the function and save its result to the cache
            result = func(*args, **kwargs)
            try:
                with open(cache_file, "wb") as f:
                    pickle.dump(result, f)
            except Exception as e:
                logger.info("Pickling failed")
            return result

        return wrapper

    return decorator


if __name__ == "__main__":

    class State:
        def __init__(self, state):
            self.state = state

    obj = State(0)

    @file_cache(ignore_params=["self", "State"])
    def example_function(self, a, b):
        return a + b + self.state

    print(example_function(obj, 1, 3))
    obj.state = 4
    print(example_function(obj, 1, 4))
    obj.state = 3
    print(example_function(obj, 1, 4))

    @file_cache()
    def example_function(self, a, b):
        return a + b + self.state

    obj.state = 0
    print(example_function(obj, 1, 3))
    obj.state = 4
    print(example_function(obj, 1, 4))
    obj.state = 3
    print(example_function(obj, 1, 4))
