import asyncio
import bisect
import inspect
from typing import TYPE_CHECKING, Any, MutableMapping, MutableSequence, Optional

from telegram import CallbackQuery, ChosenInlineResult, InlineQuery, Message, Update
from telegram.ext import ContextTypes, filters

from .. import module, util
from ..listener import Listener, ListenerFunc
from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


_LIFECYCLE_NAME_MAP = {
    "on_load": "load",
    "on_start": "start",
    "on_started": "started",
    "on_stop": "stop",
    "on_stopped": "stopped",
}


class EventDispatcher(ZyraBase):
    """Dispatches lifecycle and update events to class-module listeners."""

    listeners: MutableMapping[str, MutableSequence[Listener]]
    command_map: MutableMapping[str, Listener]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.listeners = {}
        self.command_map = {}
        super().__init__(**kwargs)

    def register_listener(
        self: "Zyra",
        mod: module.Module,
        event: str,
        func: ListenerFunc,
        *,
        priority: int = 100,
        filters_: Optional[filters.BaseFilter] = None,
        commands: tuple[str, ...] = (),
        description: Optional[str] = None,
        usage: Optional[str] = None,
    ) -> None:
        if filters_ and event in {"load", "start", "started", "stop", "stopped"}:
            self.log.warning("Built-in events can't use filters. Removing...")
            filters_ = None

        listener = Listener(
            event=event,
            func=func,
            module=mod,
            priority=priority,
            filters=filters_,
            commands=commands,
            description=description,
            usage=usage,
        )

        if event in self.listeners:
            bisect.insort(self.listeners[event], listener)
        else:
            self.listeners[event] = [listener]

        for cmd in commands:
            if cmd in self.command_map:
                other = self.command_map[cmd]
                raise module.ExistingCommandError(
                    f"Command '{cmd}' already registered by {other.module.name}"
                )
            self.command_map[cmd] = listener

        self.update_module_events()

    def unregister_listener(self: "Zyra", listener: Listener) -> None:
        lst = self.listeners.get(listener.event)
        if not lst:
            return
        if listener in lst:
            lst.remove(listener)
            if not lst:
                del self.listeners[listener.event]

        for cmd in listener.commands:
            if self.command_map.get(cmd) is listener:
                del self.command_map[cmd]

        self.update_module_events()

    def register_listeners(self: "Zyra", mod: module.Module) -> None:
        for name, func in inspect.getmembers(
            mod.__class__, predicate=inspect.isfunction
        ):
            event = getattr(func, "_listener_event", None)
            if not event:
                continue
            bound = getattr(mod, name)
            self.register_listener(
                mod,
                event,
                bound,
                priority=getattr(func, "_listener_priority", 100),
                filters_=getattr(func, "_listener_filters", None),
                commands=getattr(func, "_listener_commands", ()),
                description=getattr(func, "_listener_description", None),
                usage=getattr(func, "_listener_usage", None),
            )

        for meth_name, event in _LIFECYCLE_NAME_MAP.items():
            if hasattr(mod, meth_name):
                bound = getattr(mod, meth_name)
                if callable(bound):
                    self.register_listener(mod, event, bound, priority=0)

    def unregister_listeners(self: "Zyra", mod: module.Module) -> None:
        to_remove: list[Listener] = []
        for items in self.listeners.values():
            for listener in items:
                if listener.module == mod:
                    to_remove.append(listener)
        for listener in to_remove:
            self.unregister_listener(listener)

    async def dispatch_event(
        self: "Zyra", event: str, *args: Any, wait: bool = True, **kwargs: Any
    ) -> None:
        listeners = self.listeners.get(event)
        if not listeners:
            return

        tasks: set[asyncio.Task[Any]] = set()

        if event == "message" and args:
            update = args[0] if isinstance(args[0], Update) else None
            message: Optional[Message] = (
                update.effective_message
                if update
                else (args[0] if isinstance(args[0], Message) else None)
            )
            if message and message.text and message.text.startswith(self.prefix):
                text = message.text[len(self.prefix) :].strip()
                if text:
                    cmd = text.split()[0].lower()
                    if cmd in self.command_map:
                        listener = self.command_map[cmd]
                        if update and len(args) > 1:
                            context: ContextTypes.DEFAULT_TYPE = args[1]  # type: ignore[assignment]
                            context.user_data["_current_command"] = cmd
                            context.user_data["_current_args"] = text.split()[1:]
                        tasks.add(self.loop.create_task(listener.func(*args, **kwargs)))
                        if wait:
                            await asyncio.wait(tasks)
                        return

        for listener in listeners:
            if listener.commands and event == "message":
                continue

            if listener.filters is not None:
                matched = False
                for a in args:
                    if isinstance(a, Message) and isinstance(
                        listener.filters, filters.MessageFilter
                    ):
                        if hasattr(listener.filters, "filter"):
                            ok = await util.run_sync(listener.filters.filter, a)
                            if ok:
                                matched = True
                                break
                        else:
                            self.log.error(
                                "Filter object has no '.filter' method for event '%s'",
                                event,
                            )
                    elif isinstance(
                        a, (CallbackQuery, InlineQuery, ChosenInlineResult)
                    ):
                        self.log.error(
                            "'%s' can't be used with filters (only Message is supported)",
                            event,
                        )
                if not matched:
                    continue

            tasks.add(self.loop.create_task(listener.func(*args, **kwargs)))

        if tasks and wait:
            await asyncio.wait(tasks)

    async def log_stat(self: "Zyra", stat: str) -> None:
        await self.dispatch_event("stat_event", stat, wait=False)
