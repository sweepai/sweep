from pydantic import BaseModel

"""
The SweepConfig class is a configuration class for the Sweep application.
It contains various attributes that are used to configure the application's behavior.
"""
class SweepConfig(BaseModel):
    # A list of directories to include in the Sweep application.
    include_dirs: list[str] = []
    # A list of directories to exclude from the Sweep application.
    exclude_dirs: list[str] = [".git", "node_modules", "venv"]
    # A list of file extensions to include in the Sweep application.
    include_exts: list[str] = ['.cs', '.csharp', '.py', '.md', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs']
    # A list of file extensions to exclude from the Sweep application.
    exclude_exts: list[str] = ['.min.js', '.min.js.map', '.min.css', '.min.css.map']
    # The maximum file limit for the Sweep application.
    max_file_limit: int = 60_000

