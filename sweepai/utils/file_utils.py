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