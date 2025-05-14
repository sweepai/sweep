import time
from dataclasses import dataclass

from loguru import logger


@dataclass
class Timer:
    start: float = 0
    end: float = 0
    time_elapsed: float = -1
    do_print: bool = True

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.end = time.time()
        self.time_elapsed = self.end - self.start
        logger.debug(f"Time elapsed: {self.time_elapsed:.2f}")


if __name__ == "__main__":
    with Timer() as t:
        time.sleep(1)
    print(t.time_elapsed)
    assert t.time_elapsed > 0.9
