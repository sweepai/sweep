import base64
import chardet
from github.Repository import Repository

# attempts to decode a file with the following encodings
def read_file_with_fallback_encodings(
    file_path: str, encodings=["utf-8", "windows-1252", "iso-8859-1"]
):
    embedded_null_byte = False
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue
        except ValueError:
            embedded_null_byte = True
            continue
    if embedded_null_byte:
        raise Exception(f"Encountered null byte while decoding {file_path}")
    raise UnicodeDecodeError(
        f"Could not decode {file_path} with any of the specified encodings: {encodings}"
    )

# attempts to incode a string using the following encodings
def encode_file_with_fallback_encodings(
    file_contents: str, encodings=["utf-8", "windows-1252", "iso-8859-1"]
):
    for encoding in encodings:
        try:
            encoded_file = file_contents.encode(encoding)
            return encoded_file
        except UnicodeEncodeError:
            continue
    encodings_string = ", ".join(encodings)
    raise UnicodeEncodeError(
        f"Could not encode the file with any of the specified encodings: {encodings_string}"
    )


def safe_decode(
    repo: Repository,
    path: str,
    *args,
    **kwargs
):
    """
    By default, this function will decode the file contents from the repo.
    But if the file > 1MB, we will fetch the raw content and then decode it manually ourselves.
    It's a strange bug that occurs when the file is too large and the GitHub API doesn't decode it properly and returns encoding="none".
    Reference: https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28#get-repository-content
    """
    try:
        contents = repo.get_contents(path, *args, **kwargs)
        if contents.encoding == "none":
            blob = repo.get_git_blob(contents.sha)
            detected_encoding = chardet.detect(base64.b64decode(blob.content))['encoding']
            if detected_encoding is None:
                return None
            else:
                try:
                    return base64.b64decode(blob.content).decode(detected_encoding)
                except UnicodeDecodeError as e:
                    raise e
        return contents.decoded_content.decode("utf-8")
    except Exception as e:
        raise e