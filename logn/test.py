# relevant_new_snippet
import os
import pickle
import hashlib

from sweepai.config.server import GITHUB_BOT_USERNAME

TEST_BOT_NAME = "sweep-nightly[bot]"
MAX_DEPTH = 6


def test_returns(returns=[]):
    """Decorator to cache function output based on its inputs, ignoring specified parameters."""
    index = 0

    def decorator(func):
        def wrapper(*args, **kwargs):
            nonlocal index
            if GITHUB_BOT_USERNAME != TEST_BOT_NAME or index >= len(returns):
                result = func(*args, **kwargs)
                return result

            ret = returns[index]
            index += 1
            return ret

        return wrapper

    return decorator


if __name__ == "__main__":

    @test_returns(returns=["self", "State"])
    def example_function(a, b):
        return a + b

    print(example_function(1, 2))
    print(example_function(1, 2))
    print(example_function(1, 2))
