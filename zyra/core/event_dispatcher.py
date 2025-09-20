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
        if filters_object and event_name in LifecycleEvent.__members__.values():
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

        listener_list = self.listeners.setdefault(event_name, [])
        listener_list.append(listener_item)
        listener_list.sort()

        for command_name in commands:
            if command_name in self.command_map:
                other = self.command_map[command_name]
                raise module.ExistingCommandError(
                    f"Command '{command_name}' already registered by '{other.module.name}'"
                )

            self.command_map[command_name] = listener_item

        self.update_module_events()

    def unregister_listener(self: "Zyra", listener_item: Listener) -> None:
        listener_list = self.listeners.get(listener_item.event)
        if not listener_list:
            return

        with contextlib.suppress(ValueError):
            listener_list.remove(listener_item)

        if not listener_list:
            self.listeners.pop(listener_item.event, None)

        for command_name in listener_item.commands:
            if self.command_map.get(command_name) is listener_item:
                del self.command_map[command_name]

        self.update_module_events()

    def register_listeners(self: "Zyra", mod: module.Module) -> None:
        for attribute_name, function in inspect.getmembers(
            mod.__class__, predicate=inspect.isfunction
        ):
            if hasattr(function, "_listener_event"):
                self.register_listener(
                    mod=mod,
                    event_name=getattr(function, "_listener_event"),
                    function=getattr(mod, attribute_name),
                    priority=getattr(function, "_listener_priority", 100),
                    filters_object=getattr(function, "_listener_filters", None),
                    commands=getattr(function, "_listener_commands", ()),
                    description=getattr(function, "_listener_description", None),
                    usage=getattr(function, "_listener_usage", None),
                )

        for lifecycle in LifecycleEvent:
            method_name = f"on_{lifecycle.name.lower()}"
            if hasattr(mod, method_name) and callable(
                bound_method := getattr(mod, method_name)
            ):
                self.register_listener(
                    mod=mod,
                    event_name=lifecycle.value,
                    function=bound_method,
                    priority=0,
                )

    def unregister_listeners(self: "Zyra", mod: module.Module) -> None:
        listeners_to_remove = [
            listener_item
            for listener_group in self.listeners.values()
            for listener_item in listener_group
            if listener_item.module == mod
        ]
        for listener_item in listeners_to_remove:
            self.unregister_listener(listener_item)

    def _create_context(
        self: "Zyra",
        update: Update,
        *,
        command_name: str = "",
        raw_context: Optional[CallbackContext] = None,
    ) -> Context:
        message = update.effective_message
        if not message:
            raise ValueError("Cannot create context without effective message.")

        text = message.text or message.caption or ""
        segments = text.split()
        command_prefix_length = (
            len(self.prefix) + len(command_name)
            if command_name
            else (len(segments[0]) if segments else 0)
        )

        return Context(
            bot=self,
            message=message,
            cmd_len=command_prefix_length,
            segments=segments,
            update=update,
            _raw_ctx=raw_context,
        )

    async def _dispatch_command(
        self: "Zyra", update: Update, raw_context: Optional[CallbackContext]
    ) -> bool:
        message = update.effective_message
        message_text = message.text if message else None
        if not (message_text and message_text.startswith(self.prefix)):
            return False

        remainder = message_text[len(self.prefix) :].strip()
        if not remainder:
            return False

        command_name = remainder.split()[0].lower()
        listener_item = self.command_map.get(command_name)
        if not listener_item:
            return False

        try:
            context_obj = self._create_context(
                update, command_name=command_name, raw_context=raw_context
            )
            await listener_item.func(context_obj)
        except Exception as exc:
            traceback_obj = exc.__traceback__
            while traceback_obj and traceback_obj.tb_next:
                traceback_obj = traceback_obj.tb_next

            file_path = (
                traceback_obj.tb_frame.f_code.co_filename if traceback_obj else "?"
            )
            line_no = traceback_obj.tb_lineno if traceback_obj else "?"
            self.log.error(f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}")

        return True

    async def dispatch_event(
        self: "Zyra", event_name: str, *args: Any, **kwargs: Any
    ) -> None:
        listener_group = self.listeners.get(event_name)
        if not listener_group:
            return

        if event_name == "message" and args and isinstance(args[0], Update):
            update: Update = args[0]
            raw_context: Optional[CallbackContext] = (
                args[1]
                if len(args) > 1 and isinstance(args[1], CallbackContext)
                else None
            )
            if await self._dispatch_command(update, raw_context):
                return

        for listener_item in listener_group:
            if listener_item.commands and event_name == "message":
                continue

            if listener_item.filters and args and isinstance(args[0], Update):
                update_for_filter: Update = args[0]
                try:
                    filter_passed: bool = True
                    filter_obj = listener_item.filters
                    if hasattr(filter_obj, "check_update"):
                        # Some PTB filter implementations expose async check_update
                        maybe_result = filter_obj.check_update(update_for_filter)  # type: ignore[attr-defined]
                        if asyncio.iscoroutine(maybe_result):
                            filter_passed = await maybe_result  # type: ignore[assignment]
                        else:
                            filter_passed = bool(maybe_result)
                    elif callable(filter_obj):
                        filter_passed = bool(filter_obj(update_for_filter))  # type: ignore[misc]
                    else:
                        filter_passed = True

                    if not filter_passed:
                        continue
                except Exception as exc:
                    traceback_obj = exc.__traceback__
                    while traceback_obj and traceback_obj.tb_next:
                        traceback_obj = traceback_obj.tb_next

                    file_path = (
                        traceback_obj.tb_frame.f_code.co_filename
                        if traceback_obj
                        else "?"
                    )
                    line_no = traceback_obj.tb_lineno if traceback_obj else "?"
                    self.log.error(
                        f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}"
                    )
                    continue

            try:
                if event_name in LifecycleEvent.__members__.values():
                    await listener_item.func(*args, **kwargs)
                elif args and isinstance(args[0], Update):
                    update_for_context: Update = args[0]
                    raw_context: Optional[CallbackContext] = (
                        args[1]
                        if len(args) > 1 and isinstance(args[1], CallbackContext)
                        else None
                    )
                    context_obj = self._create_context(
                        update_for_context, raw_context=raw_context
                    )
                    await listener_item.func(context_obj)
                else:
                    await listener_item.func(*args, **kwargs)
            except Exception as exc:
                traceback_obj = exc.__traceback__
                while traceback_obj and traceback_obj.tb_next:
                    traceback_obj = traceback_obj.tb_next

                file_path = (
                    traceback_obj.tb_frame.f_code.co_filename if traceback_obj else "?"
                )
                line_no = traceback_obj.tb_lineno if traceback_obj else "?"
                self.log.error(
                    f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}"
                )

    async def log_stat(self: "Zyra", stat_key: str) -> None:
        await self.dispatch_event("stat_event", stat_key)
