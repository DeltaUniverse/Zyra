import asyncio
import logging
import sys
from typing import Any, MutableMapping

import aiorun

from .core import Zyra

log = logging.getLogger("Loader")
aiorun.logger.disabled = True


def main(config: MutableMapping[str, Any]) -> None:
    """Main entry point for the Zyra bot loader."""
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
