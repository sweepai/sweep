from pydantic import BaseModel

class SweepConfig(BaseModel):
    """
    The SweepConfig class holds various configuration options for the Sweep application.
    """
    include_dirs: list[str] = []  # List of directories to include in the Sweep application.
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]  # List of directories to exclude from the Sweep application.
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']  # List of file extensions to include in the Sweep application.
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map']  # List of file extensions to exclude from the Sweep application.
    max_file_limit: int = 60_000  # Maximum file limit for the Sweep application.

