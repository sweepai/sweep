def read_file_with_fallback_encodings(
    file_path, encodings=["utf-8", "windows-1252", "iso-8859-1"]
):
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        f"Could not decode {file_path} with any of the specified encodings: {encodings}"
    )