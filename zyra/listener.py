"""
Listener decorators and helper class for event handling in Zyra.

This module provides decorators to register functions as Telegram bot listeners
for different update types (messages, commands, callbacks, inline queries, etc.).
It also includes metadata decorators for priority, description, and usage, as
well as the Listener class to encapsulate handler information.
"""

from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence

from telegram import Message, Update
from telegram.ext import CallbackContext
from telegram.ext import filters as ptb_filters

if TYPE_CHECKING:
    from .core import Zyra

ListenerFunc = Any
Decorator = Callable[[ListenerFunc], ListenerFunc]


class Context:
    """Enhanced context object for command handling with additional utilities."""

    def __init__(
        self,
        bot: "Zyra",
        message: Message,
        cmd_len: int,
        *,
        segments: Sequence[str],
        update: Optional[Update] = None,
        ptb_context: Optional[CallbackContext] = None,
    ) -> None:
        self.bot = bot
        self.chat = message.chat
        self.msg = message
        self.message = message
        self.reply_msg = message.reply_to_message
        self.segments = segments
        self.cmd_len = cmd_len
        self.invoker = self.segments[0] if self.segments else ""
        self.last_update_time = None
        self.input = (self.msg.text or "")[self.cmd_len :]
        self.update = update
        self.ptb_context = ptb_context

    @property
    def args(self) -> Sequence[str]:
        """Get command arguments."""
        if (
            self.ptb_context is not None
            and getattr(self.ptb_context, "args", None) is not None
        ):
            return list(self.ptb_context.args)

        return self.segments[1:]

    async def respond(self, text: str, **kwargs) -> Message:
        """Send a reply message to the current chat."""
        return await self.msg.reply_text(text, **kwargs)

    async def reply(self, text: str, **kwargs) -> Message:
        """Alias for respond method."""
        return await self.respond(text, **kwargs)


def priority(_prio: int) -> Decorator:
    """Set execution priority for a listener (lower runs first)."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_priority", _prio)
        return func

    return _decorator


def desc(_desc: str) -> Decorator:
    """Add description for help system."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_description", _desc)
        return func

    return _decorator


def usage(_usage: str) -> Decorator:
    """Add usage information."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_usage", _usage)
        return func

    return _decorator


def on_message(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:
    """Register function as message event handler."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "message")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_callback_query(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:
    """Register function as callback query event handler."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "callback_query")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_inline_query(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:
    """Register function as inline query event handler."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "inline_query")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_chosen_inline_result(
    filters: Optional[ptb_filters.BaseFilter] = None,
) -> Decorator:
    """Register function as chosen inline result event handler."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "chosen_inline_result")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_chat_action(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:
    """Register function as chat action event handler."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "chat_action")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_load(func: ListenerFunc) -> ListenerFunc:
    """Register function as load event handler (called when module loads)."""
    setattr(func, "_listener_event", "load")
    return func


def on_start(func: ListenerFunc) -> ListenerFunc:
    """Register function as start event handler (called before bot starts)."""
    setattr(func, "_listener_event", "start")
    return func


def on_started(func: ListenerFunc) -> ListenerFunc:
    """Register function as started event handler (called after bot starts)."""
    setattr(func, "_listener_event", "started")
    return func


def on_stop(func: ListenerFunc) -> ListenerFunc:
    """Register function as stop event handler (called before bot stops)."""
    setattr(func, "_listener_event", "stop")
    return func


def on_stopped(func: ListenerFunc) -> ListenerFunc:
    """Register function as stopped event handler (called after bot stops)."""
    setattr(func, "_listener_event", "stopped")
    return func


def on_commands(
    *commands: str, filters: Optional[ptb_filters.BaseFilter] = None
) -> Decorator:
    """Register function as command handler for specified commands."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "message")
        setattr(func, "_listener_commands", commands)
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_command(
    command: str, filters: Optional[ptb_filters.BaseFilter] = None
) -> Decorator:
    """Register function as handler for a single command."""
    return on_commands(command, filters=filters)


class Listener:
    """
    Encapsulates a registered event listener.

    Attributes:
        event: The event type this listener handles (e.g., "message", "callback_query").
        func: The function to execute when the event is triggered.
        module: The module instance this listener belongs to.
        priority: Execution priority (lower runs first).
        filters: Optional PTB filter for event matching.
        commands: Registered commands if event is command-based.
        description: Optional description for help system.
        usage: Optional usage example for help system.
    """

    def __init__(
        self,
        event: str,
        func: ListenerFunc,
        module: Any,
        priority: int,
        filters: Optional[ptb_filters.BaseFilter] = None,
        commands: tuple[str, ...] = (),
        description: Optional[str] = None,
        usage: Optional[str] = None,
    ) -> None:
        """Initialize a new Listener instance."""
        self.event = event
        self.func = func
        self.module = module
        self.priority = priority
        self.filters = filters
        self.commands = commands
        self.description = description
        self.usage = usage

    def __lt__(self, other: "Listener") -> bool:
        """Compare listeners by priority (for sorting)."""
        return self.priority < other.priority

    def __repr__(self) -> str:
        """Return a concise string representation of the listener."""
        cmds = f" commands={self.commands}" if self.commands else ""
        return f"<Listener event={self.event} module={self.module.name}{cmds} prio={self.priority}>"
