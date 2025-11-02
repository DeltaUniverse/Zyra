import inspect
import logging
from types import ModuleType
from typing import Any, Iterable, Type

from .bus import EventBus, unwrap_method
from .events import Events, Hooks


class Module:
    __slots__ = ("bot", "log", "comment")
    name: str = "Unnamed"
    disabled: bool = False

    def __init__(self, bot: Any):
        self.bot = bot
        self.log = logging.getLogger(type(self).name.lower().replace(" ", "_"))
        self.comment = None


class Registry:
    def __init__(self, bot: Any, bus: EventBus):
        self.bot = bot
        self.bus = bus
        self.modules: dict[str, Module] = {}
        self.log = logging.getLogger("Registry")

    def _register_handlers(self, module: Module) -> None:
        cls = type(module)
        hook_values = {h.value for h in Hooks}

        for name in dir(module):
            fn = getattr(module, name, None)
            if not callable(fn):
                continue

            raw = getattr(cls, name, fn)
            base = unwrap_method(raw)

            evt = getattr(base, "_evt", None)
            flt = getattr(base, "_flt", None)
            prio = getattr(base, "_prio", 100)
            cmds = getattr(base, "_cmds", None)

            if name.startswith("on_"):
                hook = name[3:]
                if hook in hook_values:
                    self.bus.add_listener(fn, hook, filters=None, priority=prio)
                    continue

            if evt:
                if evt in hook_values and evt != Events.COMMAND.value:
                    continue

                self.bus.add_listener(fn, evt, filters=flt, priority=prio)

                if evt == Events.COMMAND.value and cmds:
                    listeners = self.bus.listeners[evt]
                    listeners[-1].commands = tuple(cmds)

    def load(self, cls: Type[Module], *, comment: str = None) -> None:
        self.log.info(f"▫️{comment or ''}{cls.name}")

        if cls.name in self.modules:
            raise ValueError(f"Module '{cls.name}' already loaded")

        module = cls(self.bot)
        module.comment = comment
        self._register_handlers(module)
        self.modules[cls.name] = module

    def unload(self, module: Module) -> None:
        self.log.info(f"Unloading module '{module.name}'")
        self.bus.remove_listeners(module)
        del self.modules[type(module).name]

    def load_package(
        self, submodules: Iterable[ModuleType], *, comment: str = None
    ) -> None:
        for module_mod in submodules:
            for sym in dir(module_mod):
                cls = getattr(module_mod, sym)
                if (
                    not inspect.isclass(cls)
                    or not issubclass(cls, Module)
                    or cls is Module
                    or getattr(cls, "disabled", False)
                ):
                    continue

                self.load(cls, comment=comment)

    def unload_all(self) -> None:
        for module in list(self.modules.values()):
            self.unload(module)
