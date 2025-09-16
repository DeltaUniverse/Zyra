"""Manages the registration, dispatching, and lifecycle of events.

This module provides the core for the bot's event-driven architecture. It
enables different modules to subscribe and react to various bot lifecycle
events (e.g., 'start', 'stop') and Telegram API events (e.g., 'message').
"""

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


# Using an Enum makes the lifecycle events more explicit and type-safe.
class LifecycleEvent(str, Enum):
    """Enumeration of bot lifecycle events."""

    LOAD = "load"
    START = "start"
    STARTED = "started"
    STOP = "stop"
    STOPPED = "stopped"


class EventDispatcher(ZyraBase):
    """Dispatches lifecycle and update events to module listeners.

    This class orchestrates all event handling, including command processing.
    It maps events to the appropriate listener functions, respects listener
    priorities, and constructs the context required by event handlers.

    Attributes:
        listeners: Maps an event name to a priority-sorted list of
            `Listener` objects.
        command_map: Maps a command name to its corresponding `Listener`
            for O(1) lookups.
    """

    listeners: MutableMapping[str, MutableSequence[Listener]]
    command_map: MutableMapping[str, Listener]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        """Initializes the EventDispatcher instance."""
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
        """Builds and registers a new event listener.

        Args:
            mod: The module instance that owns the listener.
            event: The name of the event to listen for (e.g., 'message').
            func: The coroutine function to execute when the event fires.
            priority: The listener's priority. Lower numbers execute first.
            filters_: An optional `python-telegram-bot` filter to apply.
            commands: A tuple of command names handled by this listener.
            description: An optional description for a command.
            usage: An optional usage string for a command.

        Raises:
            module.ExistingCommandError: If a command is already registered
                by another module.
        """
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
        self.listeners[event].sort()  # Sort by priority

        for cmd in commands:
            if cmd in self.command_map:
                other = self.command_map[cmd]
                raise module.ExistingCommandError(
                    f"Command '{cmd}' is already registered by module '{other.module.name}'"
                )

            self.command_map[cmd] = listener

        self.update_module_events()

    def unregister_listener(self: "Zyra", listener: Listener) -> None:
        """Unregisters a specific listener.

        Args:
            listener: The `Listener` object to unregister.
        """
        if listener.event not in self.listeners:
            return

        self.listeners[listener.event].remove(listener)
        if not self.listeners[listener.event]:
            del self.listeners[listener.event]

        for cmd in listener.commands:
            if self.command_map.get(cmd) is listener:
                del self.command_map[cmd]

        self.update_module_events()

    def register_listeners(self: "Zyra", mod: module.Module) -> None:
        """Registers all listener methods found within a given module.

        Args:
            mod: The module instance to scan for listeners.
        """
        # Register listeners defined via decorators
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

        # Register standard lifecycle hooks (e.g., on_start -> 'start' event)
        for event in LifecycleEvent:
            meth_name = f"on_{event.name.lower()}"
            if hasattr(mod, meth_name) and callable(
                bound_method := getattr(mod, meth_name)
            ):
                self.register_listener(mod, event.value, bound_method, priority=0)

    def unregister_listeners(self: "Zyra", mod: module.Module) -> None:
        """Unregisters all listeners associated with a given module."""
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
        """Constructs a `Context` object from a Telegram `Update`."""
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
        """Checks for and dispatches a command from an update, returning the task if handled."""
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
                return self.loop.create_task(listener.func(ctx))
            except Exception as e:
                self.log.error(f"Error creating context for command '{cmd}': {e}")

        return None

    async def dispatch_event(
        self: "Zyra", event: str, *args: Any, wait: bool = True, **kwargs: Any
    ) -> None:
        """Dispatches an event to all relevant listeners."""
        if event not in self.listeners:
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
                    await command_task

                return  # Command handled, no further processing needed.

        tasks: set[asyncio.Task[Any]] = set()
        for listener in self.listeners[event]:
            # Skip command listeners during general message dispatch.
            if listener.commands and event == "message":
                continue

            if listener.filters and isinstance(args[0], Update):
                if not await listener.filters.check_update(args[0]):
                    continue

            try:
                if event in LifecycleEvent.__members__.values():
                    tasks.add(self.loop.create_task(listener.func(*args)))
                elif args and isinstance(args[0], Update):
                    raw_ctx = (
                        args[1]
                        if len(args) > 1 and isinstance(args[1], CallbackContext)
                        else None
                    )
                    ctx = self._create_context(args[0], _raw_ctx=raw_ctx)
                    tasks.add(self.loop.create_task(listener.func(ctx)))
                else:
                    tasks.add(self.loop.create_task(listener.func(*args)))
            except Exception as e:
                self.log.error(
                    f"Error creating task for event '{event}' in '{listener.module.name}': {e}"
                )

        if tasks and wait:
            await asyncio.wait(tasks)

    async def log_stat(self: "Zyra", stat: str) -> None:
        """A convenience method to dispatch a 'stat_event'."""
        await self.dispatch_event("stat_event", stat, wait=False)
