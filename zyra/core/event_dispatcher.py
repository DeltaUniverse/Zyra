import asyncio
import bisect
from typing import TYPE_CHECKING, Any, MutableMapping, MutableSequence, Optional

from telegram import CallbackQuery, ChosenInlineResult, InlineQuery, Message
from telegram.ext import filters

from .. import module, util
from ..listener import Listener, ListenerFunc
from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


class EventDispatcher(ZyraBase):
    listeners: MutableMapping[str, MutableSequence[Listener]]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.listeners = {}
        super().__init__(**kwargs)

    def register_listener(
        self: "Zyra",
        mod: module.Module,
        event: str,
        func: ListenerFunc,
        *,
        priority: int = 100,
        filters_: Optional[filters.BaseFilter] = None,
    ) -> None:
        # Pastikan nama event tanpa prefix "on_"
        if event.startswith("on_"):
            event = event[3:]

        if (
            event in {"load", "start", "started", "stop", "stopped"}
            and filters_ is not None
        ):
            self.log.warning(
                "Built-in Listener can't be used with filters. Removing..."
            )
            filters_ = None

        if getattr(func, "_cmd_filters", None):
            self.log.warning(
                "@command.filters decorator only for CommandFunc. Filters will be ignored..."
            )

        if filters_:
            self.log.debug(
                "Registering filter '%s' into '%s'", type(filters_).__name__, event
            )

        listener = Listener(event, func, mod, priority, filters_)
        if event in self.listeners:
            bisect.insort(self.listeners[event], listener)
        else:
            self.listeners[event] = [listener]

        self.update_module_events()

    def unregister_listener(self: "Zyra", listener: Listener) -> None:
        self.listeners[listener.event].remove(listener)
        if not self.listeners[listener.event]:
            del self.listeners[listener.event]
        self.update_module_events()

    def register_listeners(self: "Zyra", mod: module.Module) -> None:
        got_any = False
        try:
            for event_name, func in util.misc.find_prefixed_funcs(mod, "on_"):
                if event_name.startswith("on_"):
                    event_name = event_name[3:]
                self.register_listener(
                    mod,
                    event_name,
                    func,
                    priority=getattr(func, "_listener_priority", 100),
                    filters_=getattr(func, "_listener_filters", None),
                )
                got_any = True
        except Exception as e:
            self.log.debug(
                "find_prefixed_funcs failed for %s: %r", type(mod).__name__, e
            )

        # Fallback scan manual
        if not got_any:
            for attr in dir(mod):
                if not attr.startswith("on_"):
                    continue
                func = getattr(mod, attr, None)
                if not callable(func):
                    continue
                self.register_listener(
                    mod,
                    attr[3:],  # strip "on_"
                    func,
                    priority=getattr(func, "_listener_priority", 100),
                    filters_=getattr(func, "_listener_filters", None),
                )

    def unregister_listeners(self: "Zyra", mod: module.Module) -> None:
        to_unreg = []
        for lst in self.listeners.values():
            for listener in lst:
                if listener.module == mod:
                    to_unreg.append(listener)
        for listener in to_unreg:
            self.unregister_listener(listener)

    async def dispatch_event(
        self: "Zyra", event: str, *args: Any, wait: bool = True, **kwargs: Any
    ) -> None:
        tasks = set()

        listeners = self.listeners.get(event)
        if not listeners:
            return

        args = tuple(args)
        for lst in listeners:
            if lst.filters is not None:
                matched = False
                for arg in args:
                    if isinstance(arg, Message) and isinstance(
                        lst.filters, filters.MessageFilter
                    ):
                        if hasattr(lst.filters, "filter"):
                            ok = await util.run_sync(lst.filters.filter, arg)
                            if ok:
                                matched = True
                                break
                        else:
                            self.log.error(
                                "Filter object has no '.filter' method for event '%s'",
                                event,
                            )
                    elif isinstance(
                        arg, (CallbackQuery, InlineQuery, ChosenInlineResult)
                    ):
                        self.log.error(
                            "'%s' can't be used with filters (only Message is supported)",
                            event,
                        )
                if not matched and lst.filters is not None:
                    continue

            task = self.loop.create_task(lst.func(*args, **kwargs))
            tasks.add(task)

        if not tasks:
            return

        self.log.debug("Dispatching event '%s' with data %s", event, args)
        if wait:
            await asyncio.wait(tasks)

    async def log_stat(self: "Zyra", stat: str) -> None:
        await self.dispatch_event("stat_event", stat, wait=False)
