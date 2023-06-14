import modal

if __name__ == "__main__":
    count = modal.Function.lookup("utils", "Tiktoken.count")
    print(count.call("Hello world!"))

