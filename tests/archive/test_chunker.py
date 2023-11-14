from sweepai.utils.str_utils import extract_lines
from sweepai.utils.utils import chunk_code

results = chunk_code(
    """\
import decimal
from datetime import date

class Person:
    def __init__(self, name, birth_date):
        self.name = name
        self.birth_date = birth_date

    def age(self):
        today = date.today()
        return (
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )
""",
    "file.py",
    MAX_CHARS=700,
    coalesce=200,
)

for chunk in results:
    print(extract_lines(chunk.content, chunk.start, chunk.end))
    print("\n\n============================\n\n")
