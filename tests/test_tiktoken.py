import modal

from src.utils.constants import UTILS_NAME

if __name__ == "__main__":
    count = modal.Function.lookup(UTILS_NAME, "Tiktoken.count")
    print(count.call("Hello world!"))

