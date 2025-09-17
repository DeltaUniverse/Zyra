"""Defines the base Module class and related custom exceptions.

This file provides the foundational `Module` class that all bot feature modules
should inherit from. It also defines custom exceptions used throughout the module
loading and command registration process to handle errors gracefully.
"""

import inspect
import logging
import os.path
from typing import TYPE_CHECKING, ClassVar, Optional, Type

if TYPE_CHECKING:
    from .command import Command
    from .core import Zyra


class Module:
    """The base class for all Zyra bot modules.

    Modules are self-contained units of functionality. They are automatically
    discovered and loaded by the bot.

    Attributes:
        name (ClassVar[str]): The user-facing name of the module.
        disabled (ClassVar[bool]): If True, the module will not be loaded.
        bot (Zyra): A reference to the main bot instance.
        log (logging.Logger): A logger instance specific to this module.
        comment (Optional[str]): An optional comment, often used to indicate
            if a module is 'custom'.
    """

    name: ClassVar[str] = "Unnamed"
    disabled: ClassVar[bool] = False

    bot: "Zyra"
    log: logging.Logger
    comment: Optional[str]

    def __init__(self, bot: "Zyra") -> None:
        """Initializes the Module instance.

        Args:
            bot: The main `Zyra` bot instance.
        """
        self.bot = bot
        self.log = logging.getLogger(type(self).name.lower().replace(" ", "_"))
        self.comment = None

    @classmethod
    def format_desc(cls, comment: Optional[str] = None) -> str:
        """Formats a descriptive string for the module.

        Args:
            comment: An optional comment to prepend to the description.

        Returns:
            A formatted string including the comment, module name, and file path.
        """
        _comment = comment + " " if comment else ""
        return f"{_comment}module '{cls.name}' from '{os.path.relpath(inspect.getfile(cls))}'"

    def __repr__(self) -> str:
        """Returns the formatted description of the module instance."""
        return "<" + self.format_desc(self.comment) + ">"


class ModuleLoadError(Exception):
    """Base exception for errors that occur during module loading."""


class ExistingModuleError(ModuleLoadError):
    """Exception raised when attempting to load a module that is already loaded."""

    old_module: Type[Module]
    new_module: Type[Module]

    def __init__(self, old_module: Type[Module], new_module: Type[Module]) -> None:
        """Initializes the exception.

        Args:
            old_module: The class of the module that was already loaded.
            new_module: The class of the module that failed to load.
        """
        super().__init__(
            f"Module '{old_module.name}' ({old_module.__name__}) already exists"
        )
        self.old_module = old_module
        self.new_module = new_module


class ExistingCommandError(ModuleLoadError):
    """Exception raised when a module tries to register an existing command."""

    old_cmd: "Command"
    new_cmd: "Command"
    alias: bool

    def __init__(
        self, old_cmd: "Command", new_cmd: "Command", alias: bool = False
    ) -> None:
        """Initializes the exception.

        Args:
            old_cmd: The existing command that was already registered.
            new_cmd: The new command that caused the conflict.
            alias: A boolean indicating if the conflict was due to an alias.
        """
        al_str = "alias of " if alias else ""
        old_name = type(old_cmd.module).__name__
        new_name = type(new_cmd.module).__name__
        super().__init__(
            f"Attempt to replace existing command '{old_cmd.name}' (from {old_name}) "
            f"with {al_str}'{new_cmd.name}' (from {new_name})"
        )
        self.old_cmd = old_cmd
        self.new_cmd = new_cmd
        self.alias = alias
