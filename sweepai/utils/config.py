from pydantic import BaseModel

class SweepConfig(BaseModel):
    """
    The SweepConfig class is a configuration class that holds various configuration options.
    """
    include_dirs: list[str] = []  # List of directories to include in the program
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]  # List of directories to exclude from the program
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']  # List of file extensions to include in the program
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map']  # List of file extensions to exclude from the program
    max_file_limit: int = 60_000  # Maximum file limit for the program

