from loguru import logger

# Removed the second definition of the function a_func

def a_func():
    a = 1
    b = 2 * a
    c = a * 2 + b * 3
    logger.info(f"{b}, {c}")
=======
from loguru import logger
