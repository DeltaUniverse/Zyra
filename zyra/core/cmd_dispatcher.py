"""Deprecated command dispatcher.

This module contains the `CommandDispatcher` class, which was previously used
for handling commands. Its functionality has been integrated into the
`EventDispatcher`, and this class is now a no-op for backward compatibility.
"""

from typing import TYPE_CHECKING, Any, MutableMapping

from telegram.ext import Application

from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


class CommandDispatcher(ZyraBase):
    """No-op dispatcher. Commands are now handled by EventDispatcher listeners.

    This class remains as part of the bot's inheritance structure but its
    methods do nothing except log a debug message indicating they are deprecated.
    """

    commands: MutableMapping[str, Any]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        """Initializes the no-op command dispatcher."""
        self.commands = {}
        super().__init__(**kwargs)

    def register_command(self: "Zyra", *_, **__) -> None:
        """Logs a debug message indicating this method is unused."""
        self.log.debug("register_command() is no longer used (handled by listeners)")

    def unregister_command(self: "Zyra", *_, **__) -> None:
        """Logs a debug message indicating this method is unused."""
        self.log.debug("unregister_command() is no longer used (handled by listeners)")

    def register_commands(self: "Zyra", *_, **__) -> None:
        """Logs a debug message indicating this method is unused."""
        self.log.debug("register_commands() is no longer used (handled by listeners)")

    def unregister_commands(self: "Zyra", *_, **__) -> None:
        """Logs a debug message indicating this method is unused."""
        self.log.debug("unregister_commands() is no longer used (handled by listeners)")

    async def on_command(self: "Zyra", *_, **__) -> None:
        """Logs a debug message indicating this method is unused."""
        self.log.debug("on_command() is no longer used (handled by listeners)")

    def setup_command_handler(self: "Zyra", application: Application) -> None:
        """Logs a debug message indicating this method is unused."""
        self.log.debug("setup_command_handler() is no longer used")
