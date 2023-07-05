import modal

from sweepai.utils.config import UTILS_MODAL_INST_NAME

if __name__ == "__main__":
    count = modal.Function.lookup(UTILS_MODAL_INST_NAME, "Tiktoken.count")
    print(count.call("Hello world!"))

