import inspect
import logging
from types import ModuleType
from typing import Any, Iterable, Type

from .event_bus import EventBus, unwrap_method
from .events import Events, Hooks


class ModuleBase:
    __slots__ = ("bot", "log", "comment")
    name: str = "Unnamed"
    disabled: bool = False

    def __init__(self, bot: Any):
        self.bot = bot
        self.log = logging.getLogger(type(self).name.lower().replace(" ", "_"))
        self.comment = None


class ModuleManager:
    def __init__(self, bot: Any, event_bus: EventBus):
        self.bot = bot
        self.event_bus = event_bus
        self.modules: dict[str, ModuleBase] = {}
        self.log = logging.getLogger("Module")

    def register_module_handlers(self, module: ModuleBase) -> None:
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
                    self.event_bus.add_listener(fn, hook, filters=None, priority=prio)
                    continue

            if evt:
                if evt in hook_values and evt != Events.COMMAND.value:
                    continue

                self.event_bus.add_listener(fn, evt, filters=flt, priority=prio)

                if evt == Events.COMMAND.value and cmds:
                    listeners = self.event_bus.listeners[evt]
                    listeners[-1].commands = tuple(cmds)

    def load_module(self, cls: Type[ModuleBase], *, comment: str = None) -> None:
        self.log.info(f"•{comment or ''} {cls.name}")

        if cls.name in self.modules:
            raise ValueError(f"Module '{cls.name}' already loaded")

        module = cls(self.bot)
        module.comment = comment
        self.register_module_handlers(module)
        self.modules[cls.name] = module

    def unload_module(self, module: ModuleBase) -> None:
        self.log.info(f"Unloading module '{module.name}'")
        self.event_bus.remove_listeners_for_module(module)
        del self.modules[type(module).name]

    def load_modules_from_package(
        self, submodules: Iterable[ModuleType], *, comment: str = None
    ) -> None:
        for module_mod in submodules:
            for sym in dir(module_mod):
                cls = getattr(module_mod, sym)
                if (
                    not inspect.isclass(cls)
                    or not issubclass(cls, ModuleBase)
                    or cls is ModuleBase
                    or getattr(cls, "disabled", False)
                ):
                    continue

                self.load_module(cls, comment=comment)

    def unload_all(self) -> None:
        for module in list(self.modules.values()):
            self.unload_module(module)
