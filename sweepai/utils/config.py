from pydantic import BaseModel

class SweepConfig(BaseModel):
    # List of directories to include in the sweep
    include_dirs: list[str] = []
    # List of directories to exclude from the sweep
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]
    # List of file extensions to include in the sweep
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']
    # List of file extensions to exclude from the sweep
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map']
    # Maximum file size limit for the files to be included in the sweep
    max_file_limit: int = 60_000
    max_file_limit: int = 60_000

