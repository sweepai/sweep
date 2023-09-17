# from .logn import logger
from .logn import LogTask

# TODO: fix this
from loguru import logger

logger.print = logger.info
