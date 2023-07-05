from pydantic import BaseModel

class SweepConfig(BaseModel):
    # List of directories to include when the program is running. Default is an empty list.
    include_dirs: list[str] = []
    # List of directories to exclude when the program is running. Default includes ".git", "node_modules", and "venv".
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]
    # List of file extensions to include when the program is running. Default includes '.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs'.
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']
    # List of file extensions to exclude when the program is running. Default includes '.min.js', '.min.js.map', '.min.css', '.min.css.map'.
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map']
    # Maximum number of files that can be processed. Default is 60,000.

