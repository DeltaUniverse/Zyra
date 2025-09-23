import asyncio
import contextlib
import inspect
from enum import Enum
from typing import TYPE_CHECKING, Any, MutableMapping, MutableSequence, Optional

from telegram import Update
from telegram.ext import CallbackContext, filters

from .. import module
from ..listener import Context, Listener, ListenerFunc
from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


class LifecycleEvent(str, Enum):
    LOAD = "load"
    START = "start"
    STARTED = "started"
    STOP = "stop"
    STOPPED = "stopped"


_LIFECYCLE_VALUES = {e.value for e in LifecycleEvent}


class EventDispatcher(ZyraBase):
    listeners: MutableMapping[str, MutableSequence[Listener]]
    command_map: MutableMapping[str, Listener]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.listeners = {}
        self.command_map = {}
        super().__init__(**kwargs)

    def register_listener(
        self: "Zyra",
        mod: module.Module,
        event_name: str,
        function: ListenerFunc,
        *,
        priority: int = 100,
        filters_object: Optional[filters.BaseFilter] = None,
        commands: tuple[str, ...] = (),
        description: Optional[str] = None,
        usage: Optional[str] = None,
    ) -> None:
        if filters_object and event_name in _LIFECYCLE_VALUES:
            self.log.warning("Lifecycle events ignore filters.")
            filters_object = None

        listener_item = Listener(
            event=event_name,
            func=function,
            module=mod,
            priority=priority,
            filters=filters_object,
            commands=commands,
            description=description,
            usage=usage,
        )
        bucket = self.listeners.setdefault(event_name, [])
        bucket.append(listener_item)
        bucket.sort()
        for command_name in commands:
            if command_name in self.command_map:
                other = self.command_map[command_name]
                raise module.ExistingCommandError(
                    f"Command '{command_name}' already registered by '{other.module.name}'"
                )

            self.command_map[command_name] = listener_item

        self.update_module_events()

    def unregister_listener(self: "Zyra", listener_item: Listener) -> None:
        bucket = self.listeners.get(listener_item.event)
        if not bucket:
            return

        with contextlib.suppress(ValueError):
            bucket.remove(listener_item)

        if not bucket:
            self.listeners.pop(listener_item.event, None)

        for command_name in listener_item.commands:
            if self.command_map.get(command_name) is listener_item:
                del self.command_map[command_name]

        self.update_module_events()

    def register_listeners(self: "Zyra", mod: module.Module) -> None:
        for attr_name, fn in inspect.getmembers(
            mod.__class__, predicate=inspect.isfunction
        ):
            if hasattr(fn, "_listener_event"):
                self.register_listener(
                    mod=mod,
                    event_name=getattr(fn, "_listener_event"),
                    function=getattr(mod, attr_name),
                    priority=getattr(fn, "_listener_priority", 100),
                    filters_object=getattr(fn, "_listener_filters", None),
                    commands=getattr(fn, "_listener_commands", ()),
                    description=getattr(fn, "_listener_description", None),
                    usage=getattr(fn, "_listener_usage", None),
                )

        for lifecycle in LifecycleEvent:
            method_name = f"on_{lifecycle.name.lower()}"
            if hasattr(mod, method_name) and callable(
                (bound := getattr(mod, method_name))
            ):
                self.register_listener(
                    mod=mod, event_name=lifecycle.value, function=bound, priority=0
                )

    def unregister_listeners(self: "Zyra", mod: module.Module) -> None:
        to_remove = [
            li for group in self.listeners.values() for li in group if li.module == mod
        ]
        for li in to_remove:
            self.unregister_listener(li)

    def _create_context(
        self: "Zyra",
        update: Update,
        *,
        command_name: str = "",
        raw_context: Optional[CallbackContext] = None,
    ) -> Context:
        msg = update.effective_message
        if not msg:
            raise ValueError("Cannot create context without effective message.")

        text = msg.text or msg.caption or ""
        segments = text.split()
        cmd_len = (
            len(self.prefix) + len(command_name)
            if command_name
            else len(segments[0]) if segments else 0
        )
        return Context(
            bot=self,
            message=msg,
            cmd_len=cmd_len,
            segments=segments,
            update=update,
            _raw_ctx=raw_context,
        )

    async def _dispatch_command(
        self: "Zyra", update: Update, raw_context: Optional[CallbackContext]
    ) -> bool:
        msg = update.effective_message
        text = msg.text if msg else None
        if not (text and text.startswith(self.prefix)):
            return False

        remainder = text[len(self.prefix) :].strip()
        if not remainder:
            return False

        command_name = remainder.split()[0].lower()
        listener_item = self.command_map.get(command_name)
        if not listener_item:
            return False

        try:
            ctx = self._create_context(
                update, command_name=command_name, raw_context=raw_context
            )
            await listener_item.func(ctx)
            await self.log_stat(f"cmd:{command_name}", update, raw_context)
        except Exception as exc:
            tb = exc.__traceback__
            while tb and tb.tb_next:
                tb = tb.tb_next

            file_path = tb.tb_frame.f_code.co_filename if tb else "?"
            line_no = tb.tb_lineno if tb else "?"
            self.log.error(f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}")

        return True

    async def dispatch_event(
        self: "Zyra", event_name: str, *args: Any, **kwargs: Any
    ) -> None:
        group = self.listeners.get(event_name)
        if not group:
            return

        if event_name == "message" and args and isinstance(args[0], Update):
            upd: Update = args[0]
            raw_ctx: Optional[CallbackContext] = (
                args[1]
                if len(args) > 1 and isinstance(args[1], CallbackContext)
                else None
            )
            if await self._dispatch_command(upd, raw_ctx):
                return

            await self.log_stat("msg", upd, raw_ctx)

        if event_name == "stat_event":
            for li in group:
                try:
                    await li.func(*args, **kwargs)
                except Exception as exc:
                    tb = exc.__traceback__
                    while tb and tb.tb_next:
                        tb = tb.tb_next

                    file_path = tb.tb_frame.f_code.co_filename if tb else "?"
                    line_no = tb.tb_lineno if tb else "?"
                    self.log.error(
                        f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}"
                    )

            return

        for li in group:
            if li.commands and event_name == "message":
                continue

            if li.filters and args and isinstance(args[0], Update):
                upd_for_filter: Update = args[0]
                try:
                    passed = True
                    flt = li.filters
                    if hasattr(flt, "check_update"):
                        maybe = flt.check_update(upd_for_filter)
                        passed = (
                            await maybe if asyncio.iscoroutine(maybe) else bool(maybe)
                        )
                    elif callable(flt):
                        passed = bool(flt(upd_for_filter))

                    if not passed:
                        continue
                except Exception as exc:
                    tb = exc.__traceback__
                    while tb and tb.tb_next:
                        tb = tb.tb_next

                    file_path = tb.tb_frame.f_code.co_filename if tb else "?"
                    line_no = tb.tb_lineno if tb else "?"
                    self.log.error(
                        f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}"
                    )
                    continue

            try:
                if event_name in _LIFECYCLE_VALUES:
                    await li.func(*args, **kwargs)
                elif args and isinstance(args[0], Update):
                    upd_for_ctx: Update = args[0]
                    raw_ctx: Optional[CallbackContext] = (
                        args[1]
                        if len(args) > 1 and isinstance(args[1], CallbackContext)
                        else None
                    )
                    ctx = self._create_context(upd_for_ctx, raw_context=raw_ctx)
                    await li.func(ctx)
                else:
                    await li.func(*args, **kwargs)
            except Exception as exc:
                tb = exc.__traceback__
                while tb and tb.tb_next:
                    tb = tb.tb_next

                file_path = tb.tb_frame.f_code.co_filename if tb else "?"
                line_no = tb.tb_lineno if tb else "?"
                self.log.error(
                    f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}"
                )

    async def log_stat(
        self: "Zyra",
        stat_key: str,
        update: Optional[Update] = None,
        raw_context: Optional[CallbackContext] = None,
    ) -> None:
        await self.dispatch_event("stat_event", stat_key, update, raw_context)
