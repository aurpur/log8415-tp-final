import asyncio
import logging

from deploy.config import LOG_LEVEL

from cluster.setup import setup

if __name__ == "__main__":
    logging.basicConfig(level=LOG_LEVEL)
    asyncio.run(setup())
