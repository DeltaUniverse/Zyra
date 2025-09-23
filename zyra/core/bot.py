import asyncio
import logging
from typing import Any, Mapping, Optional

import httpx
from telegram.ext import Application

from .database import DatabaseProvider
from .event_dispatcher import EventDispatcher
from .module_extender import ModuleExtender
from .telegram_bot import TelegramBot


class Zyra(TelegramBot, DatabaseProvider, EventDispatcher, ModuleExtender):
    config: Mapping[str, Any]
    application: Application
    http: httpx.AsyncClient
    lock: asyncio.Lock
    log: logging.Logger
    loop: asyncio.AbstractEventLoop
    stopping: bool
    db: DatabaseProvider

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        self.log = logging.getLogger("Bot")
        self.loop = asyncio.get_event_loop()
        self.stopping = False
        super().__init__()
        self.http = httpx.AsyncClient()

    @classmethod
    async def create_and_run(
        cls,
        config: Mapping[str, Any],
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> "Zyra":
        if loop:
            asyncio.set_event_loop(loop)

        try:
            bot = cls(config)
            await bot.setup_database()
            await bot.run()
        finally:
            asyncio.get_event_loop().stop()

    async def stop(self) -> None:
        self.stopping = True
        self.log.info("Stopping")
        if self.loaded:
            await self.dispatch_event("stop")

        try:
            await self.application.stop()
            await self.application.updater.stop()
        except Exception:
            pass

        await self.close_database()
        await self.http.aclose()
        self.log.info("Running post-stop hooks")
        if self.loaded:
            await self.dispatch_event("stopped")
