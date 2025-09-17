import asyncio
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
        event: str,
        func: ListenerFunc,
        *,
        priority: int = 100,
        filters_: Optional[filters.BaseFilter] = None,
        commands: tuple[str, ...] = (),
        description: Optional[str] = None,
        usage: Optional[str] = None,
    ) -> None:
        if filters_ and event in LifecycleEvent.__members__.values():
            self.log.warning(
                "Lifecycle events do not support filters. Ignoring filter."
            )
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

        self.listeners.setdefault(event, []).append(listener)
        self.listeners[event].sort()

        for cmd in commands:
            if cmd in self.command_map:
                other = self.command_map[cmd]
                raise module.ExistingCommandError(
                    f"Command '{cmd}' is already registered by module '{other.module.name}'"
                )

            self.command_map[cmd] = listener

        self.update_module_events()

    def unregister_listener(self: "Zyra", listener: Listener) -> None:
        if listener.event not in self.listeners:
            return

        try:
            self.listeners[listener.event].remove(listener)
        except ValueError:
            return

        if not self.listeners[listener.event]:
            del self.listeners[listener.event]

        for cmd in listener.commands:
            if self.command_map.get(cmd) is listener:
                del self.command_map[cmd]

        self.update_module_events()

    def register_listeners(self: "Zyra", mod: module.Module) -> None:
        for name, func in inspect.getmembers(
            mod.__class__, predicate=inspect.isfunction
        ):
            if hasattr(func, "_listener_event"):
                self.register_listener(
                    mod,
                    getattr(func, "_listener_event"),
                    getattr(mod, name),
                    priority=getattr(func, "_listener_priority", 100),
                    filters_=getattr(func, "_listener_filters", None),
                    commands=getattr(func, "_listener_commands", ()),
                    description=getattr(func, "_listener_description", None),
                    usage=getattr(func, "_listener_usage", None),
                )

        for event in LifecycleEvent:
            meth_name = f"on_{event.name.lower()}"
            if hasattr(mod, meth_name) and callable(
                bound_method := getattr(mod, meth_name)
            ):
                self.register_listener(mod, event.value, bound_method, priority=0)

    def unregister_listeners(self: "Zyra", mod: module.Module) -> None:
        to_remove = [
            listener
            for listeners in self.listeners.values()
            for listener in listeners
            if listener.module == mod
        ]
        for listener in to_remove:
            self.unregister_listener(listener)

    def _create_context(
        self: "Zyra",
        update: Update,
        *,
        command: str = "",
        _raw_ctx: Optional[CallbackContext] = None,
    ) -> Context:
        message = update.effective_message
        if not message:
            raise ValueError(
                "Cannot create context from an update with no effective message."
            )

        text = message.text or message.caption or ""
        segments = text.split()
        cmd_len = (
            len(self.prefix) + len(command)
            if command
            else (len(segments[0]) if segments else 0)
        )

        return Context(
            bot=self,
            message=message,
            cmd_len=cmd_len,
            segments=segments,
            update=update,
            _raw_ctx=_raw_ctx,
        )

    async def _dispatch_command(
        self: "Zyra", update: Update, raw_ctx: Optional[CallbackContext]
    ) -> Optional[asyncio.Task]:
        message = update.effective_message
        if not (message and message.text and message.text.startswith(self.prefix)):
            return None

        command_text = message.text[len(self.prefix) :].strip()
        if not command_text:
            return None

        cmd = command_text.split()[0].lower()
        listener = self.command_map.get(cmd)

        if listener:
            try:
                ctx = self._create_context(update, command=cmd, _raw_ctx=raw_ctx)
                await listener.func(ctx)
            except Exception as e:
                self.log.error(f"Error creating context for command '{cmd}': {e}")

        return None

    async def dispatch_event(
        self: "Zyra", event: str, *args: Any, wait: bool = True, **kwargs: Any
    ) -> None:
        try:
            listeners = self.listeners[event]
        except KeyError:
            return

        if not listeners:
            return

        if event == "message" and args and isinstance(args[0], Update):
            update, raw_ctx = args[0], (
                args[1]
                if len(args) > 1 and isinstance(args[1], CallbackContext)
                else None
            )
            command_task = await self._dispatch_command(update, raw_ctx)
            if command_task:
                if wait:
                    try:
                        await command_task
                    except Exception as e:
                        self.log.error(f"Error in command execution: {e}")

                return

        tasks = set()
        for listener in listeners:
            if listener.commands and event == "message":
                continue

            if listener.filters and args and isinstance(args[0], Update):
                try:
                    if not await listener.filters.check_update(args[0]):
                        continue
                except Exception as e:
                    self.log.error(f"Error checking filter: {e}")
                    continue

            try:
                if event in LifecycleEvent.__members__.values():
                    task = self.loop.create_task(listener.func(*args))
                elif args and isinstance(args[0], Update):
                    raw_ctx = (
                        args[1]
                        if len(args) > 1 and isinstance(args[1], CallbackContext)
                        else None
                    )
                    ctx = self._create_context(args[0], _raw_ctx=raw_ctx)
                    task = self.loop.create_task(listener.func(ctx))
                else:
                    task = self.loop.create_task(listener.func(*args))

                tasks.add(task)
            except Exception as e:
                self.log.error(f"Error creating task for '{listener.module.name}': {e}")

        if tasks and wait:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
            for task in done:
                try:
                    await task
                except Exception as e:
                    self.log.error(f"Error in event listener: {e}")

    async def log_stat(self: "Zyra", stat: str) -> None:
        await self.dispatch_event("stat_event", stat, wait=False)
