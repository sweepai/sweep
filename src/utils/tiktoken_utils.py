import tiktoken


def count_tokens(text: str) -> int:
    encoding = tiktoken.encoding_for_model("gpt-4")
    try:
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        print(f"Error: {e}")
        return 0
