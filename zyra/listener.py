"""Listener decorators and helper classes for event handling.

This module provides the primary tools for creating event-driven modules. It
includes a suite of decorators to register functions as handlers for various
Telegram events (e.g., messages, commands, callbacks) and bot lifecycle events
(e.g., load, start, stop).

It also defines the `Context` class, which provides a convenient, unified
interface for interacting with incoming events, and the `Listener` class,
which encapsulates the metadata for each registered handler.
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
    """Provides a convenient interface for interacting with an incoming event.

    This class wraps a `telegram.Update` and `telegram.Message` object, offering
    helper attributes and methods to simplify common tasks like accessing message
    text, parsing arguments, and sending replies.

    Attributes:
        bot (Zyra): The main bot instance.
        chat (telegram.Chat): The chat where the event occurred.
        msg (telegram.Message): The message associated with the event.
        message (telegram.Message): An alias for `msg`.
        reply_msg (Optional[telegram.Message]): The message this message is a reply to.
        segments (Sequence[str]): The message text split into a list of words.
        cmd_len (int): The character length of the command that was invoked.
        invoker (str): The command or first word of the message.
        input (str): The raw text of the message after the command.
        update (Optional[telegram.Update]): The raw `Update` object from PTB.
        ptb_context (Optional[CallbackContext]): The raw `CallbackContext` from PTB.
    """

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
        """Initializes the Context object.

        Args:
            bot: The main bot instance.
            message: The message object from the update.
            cmd_len: The length of the invoked command in the message text.
            segments: The message text split by whitespace.
            update: The raw `Update` object.
            ptb_context: The raw `CallbackContext` object.
        """
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
        """Returns the command arguments as a list of strings."""
        if (
            self.ptb_context is not None
            and getattr(self.ptb_context, "args", None) is not None
        ):
            return list(self.ptb_context.args)

        return self.segments[1:]

    async def respond(self, text: str, **kwargs) -> Message:
        """Sends a message in response to the original message.

        This method replies directly to the message that triggered the event.

        Args:
            text: The text content of the message to send.
            **kwargs: Additional keyword arguments to pass to `telegram.Message.reply_text`.

        Returns:
            The `telegram.Message` object that was sent.
        """
        return await self.msg.reply_text(text, **kwargs)

    async def reply(self, text: str, **kwargs) -> Message:
        """Alias for the `respond` method."""
        return await self.respond(text, **kwargs)


def priority(_prio: int) -> Decorator:
    """Decorator to set the execution priority for a listener.

    Listeners with a lower priority number are executed before those with a
    higher number. The default is 100.

    Args:
        _prio: An integer representing the priority.
    """

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_priority", _prio)
        return func

    return _decorator


def desc(_desc: str) -> Decorator:
    """Decorator to add a description to a command listener for help systems.

    Args:
        _desc: A string describing the command.
    """

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_description", _desc)
        return func

    return _decorator


def usage(_usage: str) -> Decorator:
    """Decorator to add usage information to a command listener.

    Args:
        _usage: A string showing how to use the command (e.g., "<user> [reason]").
    """

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_usage", _usage)
        return func

    return _decorator


def on_message(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:
    """Decorator to register a function as a message event handler.

    Args:
        filters: An optional `python-telegram-bot` filter to apply.
    """

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "message")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_callback_query(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:
    """Decorator to register a function as a callback query event handler.

    Args:
        filters: An optional `python-telegram-bot` filter to apply.
    """

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "callback_query")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_inline_query(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:
    """Decorator to register a function as an inline query event handler.

    Args:
        filters: An optional `python-telegram-bot` filter to apply.
    """

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "inline_query")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_chosen_inline_result(
    filters: Optional[ptb_filters.BaseFilter] = None,
) -> Decorator:
    """Decorator to register a function as a chosen inline result event handler.

    Args:
        filters: An optional `python-telegram-bot` filter to apply.
    """

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "chosen_inline_result")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_chat_action(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:
    """Decorator to register a function as a chat action event handler.

    Chat actions include events like a user joining or leaving a group.

    Args:
        filters: An optional `python-telegram-bot` filter to apply.
    """

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "chat_action")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_load(func: ListenerFunc) -> ListenerFunc:
    """Decorator to register a function to run when its module is loaded."""
    setattr(func, "_listener_event", "load")
    return func


def on_start(func: ListenerFunc) -> ListenerFunc:
    """Decorator to register a function to run just before the bot starts polling."""
    setattr(func, "_listener_event", "start")
    return func


def on_started(func: ListenerFunc) -> ListenerFunc:
    """Decorator to register a function to run right after the bot has started."""
    setattr(func, "_listener_event", "started")
    return func


def on_stop(func: ListenerFunc) -> ListenerFunc:
    """Decorator to register a function to run just before the bot stops."""
    setattr(func, "_listener_event", "stop")
    return func


def on_stopped(func: ListenerFunc) -> ListenerFunc:
    """Decorator to register a function to run after the bot has fully stopped."""
    setattr(func, "_listener_event", "stopped")
    return func


def on_commands(
    *commands: str, filters: Optional[ptb_filters.BaseFilter] = None
) -> Decorator:
    """Decorator to register a function as a handler for multiple commands.

    Args:
        *commands: A sequence of command names (without the prefix) to register.
        filters: An optional `python-telegram-bot` filter to apply.
    """

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
    """Decorator to register a function as a handler for a single command.

    Args:
        command: The command name (without the prefix).
        filters: An optional `python-telegram-bot` filter to apply.
    """
    return on_commands(command, filters=filters)


class Listener:
    """A data class that encapsulates a registered event listener.

    This class holds all the metadata associated with a listener function,
    such as its event type, priority, associated commands, and filters.

    Attributes:
        event: The name of the event this listener handles (e.g., "message").
        func: The coroutine function to execute when the event is triggered.
        module: The module instance this listener belongs to.
        priority: The execution priority (lower numbers run first).
        filters: An optional `python-telegram-bot` filter for event matching.
        commands: A tuple of command names if the listener is a command handler.
        description: An optional description for the listener, used in help systems.
        usage: An optional usage string, used in help systems.
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
        """Initializes a new Listener instance."""
        self.event = event
        self.func = func
        self.module = module
        self.priority = priority
        self.filters = filters
        self.commands = commands
        self.description = description
        self.usage = usage

    def __lt__(self, other: "Listener") -> bool:
        """Compares listeners based on their priority for sorting."""
        return self.priority < other.priority

    def __repr__(self) -> str:
        """Returns a concise string representation of the listener."""
        cmds = f" commands={self.commands}" if self.commands else ""
        return f"<Listener event={self.event} module={self.module.name}{cmds} prio={self.priority}>"
