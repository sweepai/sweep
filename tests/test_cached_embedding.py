from diskcache import Cache, FanoutCache
from sweepai.utils.constants import DB_NAME
import hashlib

from sweepai.utils.hash import hash_sha256

cache = Cache("tests/data/test_cache")
import pdb; pdb.set_trace()

# letters = ["a", "b", "c", "d", "e", "f", "g", "h", "i"]

# for letter in letters:
#     cache.set(hash_sha256(letter), letter)

# for letter in letters:
#     assert cache.get(hash(letter)) == letter


