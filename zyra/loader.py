"""Initializes the asyncio event loop and runs the bot.

This module is responsible for setting up the appropriate high-performance
asyncio event loop policy (`uvloop` on Linux/macOS, `Proactor` on Windows)
and then using `aiorun` to start and manage the bot's lifecycle.
"""

import asyncio
import logging
import sys
from typing import Any, MutableMapping

import aiorun

from .core import Zyra

log = logging.getLogger("Loader")
aiorun.logger.disabled = True


def main(config: MutableMapping[str, Any]) -> None:
    """Sets up the event loop and starts the Zyra bot.

    This function selects the optimal asyncio event loop for the current
    operating system, creates a new loop, and then starts the bot's asynchronous
    `create_and_run` lifecycle using the `aiorun` library.

    Args:
        config: The bot's configuration dictionary.
    """
    if sys.platform == "win32":
        policy = asyncio.WindowsProactorEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
    else:
        try:
            import uvloop
        except ImportError:
            pass
        else:
            uvloop.install()
            log.info("Using uvloop event loop")

    log.info("Initializing Zyra bot")
    loop = asyncio.new_event_loop()

    # run lifecycle until stop
    try:
        aiorun.run(Zyra.create_and_run(config, loop=loop), loop=loop)
    except Exception as e:
        log.error(f"Failed to start Zyra: {e}")
        raise
