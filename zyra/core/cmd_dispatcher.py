from typing import TYPE_CHECKING, Any, MutableMapping

from telegram.ext import Application

from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


class CommandDispatcher(ZyraBase):
    """No-op dispatcher. Commands are now handled by EventDispatcher listeners."""

    commands: MutableMapping[str, Any]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.commands = {}
        super().__init__(**kwargs)

    def register_command(self: "Zyra", *_, **__) -> None:
        self.log.debug("register_command() is no longer used (handled by listeners)")

    def unregister_command(self: "Zyra", *_, **__) -> None:
        self.log.debug("unregister_command() is no longer used (handled by listeners)")

    def register_commands(self: "Zyra", *_, **__) -> None:
        self.log.debug("register_commands() is no longer used (handled by listeners)")

    def unregister_commands(self: "Zyra", *_, **__) -> None:
        self.log.debug("unregister_commands() is no longer used (handled by listeners)")

    async def on_command(self: "Zyra", *_, **__) -> None:
        self.log.debug("on_command() is no longer used (handled by listeners)")

    def setup_command_handler(self: "Zyra", application: Application) -> None:
        self.log.debug("setup_command_handler() is no longer used")
