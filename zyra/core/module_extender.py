"""Module for extending the bot with module-loading capabilities."""

import importlib
import inspect
from types import ModuleType
from typing import TYPE_CHECKING, Any, Iterable, MutableMapping, Optional, Type

from .. import custom_modules, module, modules, util
from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


class ModuleExtender(ZyraBase):
    """A mixin for the Zyra bot that handles loading, unloading, and reloading modules."""

    # Initialized during instantiation
    modules: MutableMapping[str, module.Module]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        """Initialize the ModuleExtender.

        Args:
            **kwargs: Keyword arguments to pass to the parent class initializer.
        """
        self.modules = {}
        super().__init__(**kwargs)

    def load_module(
        self: "Zyra", cls: Type[module.Module], *, comment: Optional[str] = None
    ) -> None:
        """Load a single module.

        Instantiates the provided module class, registers its listeners and
        commands, and adds it to the bot's collection of active modules.

        Args:
            cls: The module class to load.
            comment: An optional comment for logging (e.g., "custom").

        Raises:
            module.ExistingModuleError: If a module with the same name is
                already loaded.
        """
        self.log.info("Loading %s", cls.format_desc(comment))

        if cls.name in self.modules:
            old = type(self.modules[cls.name])
            raise module.ExistingModuleError(old, cls)

        mod = cls(self)
        mod.comment = comment
        self.register_listeners(mod)
        self.register_commands(mod)
        self.modules[cls.name] = mod

    def unload_module(self: "Zyra", mod: module.Module) -> None:
        """Unload a single module.

        Unregisters the module's listeners and commands and removes it from
        the bot's collection of active modules.

        Args:
            mod: The module instance to unload.
        """
        cls = type(mod)
        self.log.info("Unloading %s", mod.format_desc(mod.comment))

        self.unregister_listeners(mod)
        self.unregister_commands(mod)
        del self.modules[cls.name]

    def _load_all_from_metamod(
        self: "Zyra", submodules: Iterable[ModuleType], *, comment: Optional[str] = None
    ) -> None:
        """Scan a package and load all valid module classes found within.

        This is a helper function to iterate through a given package's
        submodules, find classes that are subclasses of `module.Module`,
        and load them.

        Args:
            submodules: An iterable of module types to scan for module classes.
            comment: An optional comment to be passed to `load_module`.
        """
        for module_mod in submodules:
            for sym in dir(module_mod):
                cls = getattr(module_mod, sym)
                if not (inspect.isclass(cls) and issubclass(cls, module.Module)):
                    continue
                if getattr(cls, "disabled", False):
                    # Use format_desc for consistent path + name
                    self.log.info("Skipping %s", cls.format_desc(comment))
                    continue
                self.load_module(cls, comment=comment)

    def load_all_modules(self: "Zyra") -> None:
        """Load all standard and custom modules."""
        self.log.info("Loading modules")
        self._load_all_from_metamod(modules.submodules)
        self._load_all_from_metamod(custom_modules.submodules, comment="custom")
        self.log.info("All modules loaded.")

    def unload_all_modules(self: "Zyra") -> None:
        """Unload all currently loaded modules."""
        self.log.info("Unloading modules...")

        for mod in list(self.modules.values()):
            self.unload_module(mod)

        self.log.info("All modules unloaded.")

    async def reload_module_pkg(self: "Zyra") -> None:
        """Reload the core module packages.

        This is primarily intended for development to apply changes to the
        base module class or the module discovery mechanism without needing
        to restart the entire bot.
        """
        self.log.info("Reloading base module class...")
        await util.run_sync(importlib.reload, module)

        self.log.info("Reloading master module...")
        await util.run_sync(importlib.reload, modules)
