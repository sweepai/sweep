

import os
import string
from typing import Literal, Self, Type
from sweepai.core.entities import FileChangeRequest, RegexMatchableBaseModel


example = """*` `test.py`: Add a check to ensure that the 'Url *' index exists # $"""

fcr = FileChangeRequest.from_string(example)
assert fcr.filename == "test.py"
assert fcr.instructions == fcr.instructions.strip()∂