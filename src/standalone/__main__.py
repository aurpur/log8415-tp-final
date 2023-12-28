import logging

from common.config import LOG_LEVEL

from standalone.setup import setup

if __name__ == "__main__":
    logging.basicConfig(level=LOG_LEVEL)
    setup()


