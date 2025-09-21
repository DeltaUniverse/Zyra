"""The main bot class and entry point.

This module defines the `Zyra` class, which integrates all the components
(Telegram client, event dispatcher, module loader) into a single, cohesive
application. It also provides the main method to create and run the bot.
"""

import asyncio
import logging
from typing import Any, Mapping, Optional

import httpx
from telegram.ext import Application

from .cmd_dispatcher import CommandDispatcher
from .database import DatabaseProvider
from .event_dispatcher import EventDispatcher
from .module_extender import ModuleExtender
from .telegram_bot import TelegramBot


class Zyra(
    TelegramBot, CommandDispatcher, DatabaseProvider, EventDispatcher, ModuleExtender
):
    """The main bot class, integrating all core components.

    This class inherits functionality from various mixins to handle Telegram
    communication, event dispatching, command handling, and module loading.
    It manages the bot's state, configuration, and lifecycle.

    Attributes:
        config (Mapping[str, Any]): The bot's configuration dictionary.
        application (Application): The `python-telegram-bot` Application instance.
        http (httpx.AsyncClient): An asynchronous HTTP client for making web requests.
        lock (asyncio.Lock): A lock for managing concurrent operations.
        log (logging.Logger): The logger instance for the bot.
        loop (asyncio.AbstractEventLoop): The asyncio event loop.
        stopping (bool): A flag indicating if the bot is in the process of shutting down.
    """

    config: Mapping[str, Any]
    application: Application
    http: httpx.AsyncClient
    lock: asyncio.Lock
    log: logging.Logger
    loop: asyncio.AbstractEventLoop
    stopping: bool
    db: DatabaseProvider

    def __init__(self, config: Mapping[str, Any]) -> None:
        """Initializes the Zyra bot.

        Args:
            config: A mapping containing the bot's configuration, including
                API tokens and other settings.
        """
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
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> "Zyra":
        """Creates a bot instance and runs it.

        This is the primary entry point for starting the bot. It handles instance
        creation, running the main event loop, and ensuring cleanup on exit.

        Args:
            config: The bot's configuration mapping.
            loop: An optional existing asyncio event loop to use.

        Returns:
            The created and run `Zyra` instance.
        """

        if loop:
            asyncio.set_event_loop(loop)

        try:
            bot = cls(config)
            # Initialize database before running
            await bot.setup_database()
            await bot.run()
        finally:
            asyncio.get_event_loop().stop()

    async def stop(self) -> None:
        """Gracefully stops the bot and all its components.

        This method dispatches 'stop' and 'stopped' lifecycle events, stops the
        Telegram polling, closes the HTTP client, and performs necessary cleanup.
        """
        self.stopping = True
        self.log.info("Stopping")

        if self.loaded:
            await self.dispatch_event("stop")

        try:
            await self.application.stop()
            await self.application.updater.stop()
        except Exception:
            pass

        # Use the new close_database method
        await self.close_database()
        await self.http.aclose()

        self.log.info("Running post-stop hooks")
        if self.loaded:
            await self.dispatch_event("stopped")
