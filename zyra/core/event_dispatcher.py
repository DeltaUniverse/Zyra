"""Handles the registration, management, and dispatching of events.

This module is the core of the bot's event-driven architecture. It allows
different parts of the bot (modules) to listen and react to various lifecycle
and Telegram events, including messages and commands.
"""

import asyncio
import bisect
import inspect
from typing import TYPE_CHECKING, Any, MutableMapping, MutableSequence, Optional

from telegram import CallbackQuery, ChosenInlineResult, InlineQuery, Message, Update
from telegram.ext import filters

from .. import module, util
from ..listener import Context, Listener, ListenerFunc
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
    """Dispatches lifecycle and update events to class-module listeners.

    This class manages all event listeners, including command handlers. It maps
    events to listener functions, handles listener priorities, and creates
    the context for event handlers.

    Attributes:
        listeners (MutableMapping[str, MutableSequence[Listener]]): A dictionary
            mapping event names to a sorted list of `Listener` objects.
        command_map (MutableMapping[str, Listener]): A dictionary mapping
            command names to their corresponding `Listener` object for quick
            lookup.
    """

    listeners: MutableMapping[str, MutableSequence[Listener]]
    command_map: MutableMapping[str, Listener]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        """Initializes the EventDispatcher."""
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
        """Registers a new event listener.

        Creates a `Listener` object and adds it to the internal listeners mapping.
        If the listener is for a command, it's also added to the command map.

        Args:
            mod: The module instance that owns the listener.
            event: The name of the event to listen for (e.g., 'message').
            func: The coroutine function to be called when the event occurs.
            priority: The priority of the listener. Lower numbers run first.
            filters_: An optional `python-telegram-bot` filter to apply.
            commands: A tuple of command names associated with this listener.
            description: An optional description for the command.
            usage: An optional usage string for the command.

        Raises:
            module.ExistingCommandError: If a command is already registered
                by another module.
        """
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
        """Unregisters a specific listener.

        Removes the listener from the event listeners list and from the
        command map if it's a command listener.

        Args:
            listener: The `Listener` object to unregister.
        """
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
        """Registers all listeners found within a given module.

        Scans a module instance for methods decorated as listeners and
        registers them. Also registers standard lifecycle methods like
        `on_load` and `on_start`.

        Args:
            mod: The module instance to scan for listeners.
        """
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
        """Unregisters all listeners associated with a given module.

        Args:
            mod: The module whose listeners should be unregistered.
        """
        to_remove: list[Listener] = []
        for items in self.listeners.values():
            for listener in items:
                if listener.module == mod:
                    to_remove.append(listener)

        for listener in to_remove:
            self.unregister_listener(listener)

    def _create_context(
        self: "Zyra", update: Update, command: str = "", cmd_len: int = 0
    ) -> Context:
        """Creates a Context object from a Telegram Update.

        This helper function parses an `Update` to extract relevant information
        like the message text and command arguments, and encapsulates it in a
        `Context` object for easy use in handlers.

        Args:
            update: The incoming `Update` from `python-telegram-bot`.
            command: The name of the command being executed, if any.
            cmd_len: The length of the command text in the message.

        Returns:
            A `Context` object populated with data from the update.

        Raises:
            ValueError: If the update does not contain an effective message.
        """
        if not update.effective_message:
            raise ValueError("Update has no effective message")

        message = update.effective_message
        text = message.text or ""

        # Parse command and arguments
        if text.startswith(self.prefix) and command:
            segments = text[len(self.prefix) :].strip().split()
            cmd_len = len(self.prefix) + len(command)
        else:
            segments = text.split() if text else []
            cmd_len = len(segments[0]) if segments else 0

        return Context(
            bot=self,
            message=message,
            cmd_len=cmd_len,
            segments=segments,
            update=update,
            ptb_context=None,
        )

    async def dispatch_event(
        self: "Zyra", event: str, *args: Any, wait: bool = True, **kwargs: Any
    ) -> None:
        """Dispatches an event to all registered listeners.

        Finds all listeners for a given event and executes them. It handles
        command detection, context creation, and filter application.

        Args:
            event: The name of the event to dispatch.
            *args: Positional arguments to pass to the listener functions.
                Typically, this will be the `Update` object.
            wait: If `True`, waits for all listener tasks to complete.
            **kwargs: Keyword arguments (currently unused).
        """
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
                        # Create context for command handlers
                        try:
                            ctx = self._create_context(
                                update, cmd, len(self.prefix) + len(cmd)
                            )
                            tasks.add(self.loop.create_task(listener.func(ctx)))
                            if wait:
                                await asyncio.wait(tasks)

                            return
                        except Exception as e:
                            self.log.error(
                                f"Error creating context for command '{cmd}': {e}"
                            )
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

            # For lifecycle events (load, start, etc.), pass the listener function directly
            if event in {"load", "start", "started", "stop", "stopped"}:
                if args:
                    tasks.add(self.loop.create_task(listener.func(*args)))
                else:
                    tasks.add(self.loop.create_task(listener.func()))
            # For other events, create context if it's an Update
            elif args and isinstance(args[0], Update):
                try:
                    ctx = self._create_context(args[0])
                    tasks.add(self.loop.create_task(listener.func(ctx)))
                except Exception as e:
                    self.log.error(f"Error creating context for event '{event}': {e}")
                    # Fallback to passing the update directly
                    tasks.add(self.loop.create_task(listener.func(args[0])))
            else:
                # For non-Update events, pass arguments as-is
                tasks.add(self.loop.create_task(listener.func(*args)))

        if tasks and wait:
            await asyncio.wait(tasks)

    async def log_stat(self: "Zyra", stat: str) -> None:
        """Dispatches a special statistics event.

        This is a convenience method for logging stats, which triggers the
        'stat_event' for any interested listeners.

        Args:
            stat: The name of the statistic to log.
        """
        await self.dispatch_event("stat_event", stat, wait=False)
