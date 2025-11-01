import asyncio
import logging
from typing import Any, Mapping

import httpx

from .. import custom_modules, modules
from ..util import time
from .database import Database
from .event_bus import EventBus
from .events import Hooks
from .module_manager import ModuleManager
from .telegram_interface import TelegramInterface


class Zyra:
    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        self.log = logging.getLogger("Bot")
        self.loop = asyncio.get_running_loop()
        self.stopping = False
        self.loaded = False
        self.start_time_us = 0

        bot_config = config.get("bot", {})
        tg_config = config["telegram"]

        db_uri = bot_config.get("db_uri")
        if not db_uri:
            raise SystemExit("Missing bot.db_uri in config")

        prefixes = bot_config.get("prefix", "/")
        prefixes = (
            tuple(prefixes)
            if isinstance(prefixes, (list, tuple, set))
            else (str(prefixes),)
        )

        self.db = Database(db_uri)
        self.event_bus = EventBus(self, prefixes)
        self.module_manager = ModuleManager(self, self.event_bus)
        self.telegram = TelegramInterface(
            token=tg_config["token"],
            event_bus=self.event_bus,
            owner_id=config["rank"]["owner_id"],
            log=self.log,
            base_url=tg_config.get("base_url"),
        )

        self.http = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            timeout=httpx.Timeout(15.0),
            http2=False,
        )

    @property
    def owner_id(self) -> int:
        return self.telegram.owner_id

    @property
    def sudoers(self) -> set[int]:
        return self.telegram.sudoers

    @property
    def bot_username(self) -> str:
        return self.telegram.bot_username

    @property
    def me(self):
        return self.telegram.me

    @property
    def client(self):
        return self.telegram.client

    async def start(self) -> None:
        self.log.info("Starting")

        await self.db.connect()
        await self.telegram.initialize(self.db.pool)

        self.log.info("Loading modules")
        self.module_manager.load_modules_from_package(modules.submodules)
        self.module_manager.load_modules_from_package(
            custom_modules.submodules, comment="custom"
        )
        self.log.info("All modules loaded")

        await self.event_bus.emit_hook(Hooks.LOAD)
        self.loaded = True

        self.telegram.bind_handlers()
        await self.telegram.start()

        self.start_time_us = time.usec()
        await self.event_bus.emit_hook(Hooks.START)
        self.log.info("Bot is ready")
        await self.event_bus.emit_hook(Hooks.STARTED)

    async def stop(self) -> None:
        if self.stopping:
            return

        self.stopping = True
        self.log.info("Stopping")

        if self.loaded:
            await self.event_bus.emit_hook(Hooks.STOP)

        await self.telegram.stop()
        await self.cleanup()

        if self.loaded:
            await self.event_bus.emit_hook(Hooks.STOPPED)

    async def cleanup(self) -> None:
        await self.db.close()
        await self.http.aclose()

    async def run(self) -> None:
        try:
            await self.start()
            await self.telegram.idle(self.loop)
        finally:
            await self.stop()

    @classmethod
    async def create_and_run(cls, config: Mapping[str, Any]) -> "Zyra":
        bot = cls(config)
        try:
            await bot.run()
        finally:
            asyncio.get_event_loop().stop()

    def redact_message(self, text: str) -> str:
        bot_token = self.config["telegram"].get("token")
        if bot_token and bot_token in text:
            return text.replace(bot_token, "[REDACTED]")

        return text
