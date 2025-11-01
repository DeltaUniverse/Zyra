import asyncio
import logging
import sys
from typing import Any, MutableMapping

import aiorun

from .core.bot import Zyra

log = logging.getLogger("Loader")
aiorun.logger.disabled = True


def run_bot(config: MutableMapping[str, Any]) -> None:
    if sys.platform == "win32":
        policy = asyncio.WindowsProactorEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
    else:
        try:
            import uvloop

            uvloop.install()
            log.info("Using uvloop event loop")
        except ImportError:
            pass

    log.info("Initializing Zyra bot")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        aiorun.run(Zyra.create_and_run(config), loop=loop)
    except KeyboardInterrupt:
        log.info("Received keyboard interrupt")
    except Exception as e:
        log.error(f"Failed to start Zyra: {e}", exc_info=True)
        raise
