# zyra/core/listener.py

from typing import Any, Callable, Optional

from telegram.ext import filters as ptb_filters

ListenerFunc = Any
Decorator = Callable[[ListenerFunc], ListenerFunc]


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
    """Register function as load event handler."""
    setattr(func, "_listener_event", "load")
    return func


def on_start(func: ListenerFunc) -> ListenerFunc:
    """Register function as start event handler."""
    setattr(func, "_listener_event", "start")
    return func


def on_started(func: ListenerFunc) -> ListenerFunc:
    """Register function as started event handler."""
    setattr(func, "_listener_event", "started")
    return func


def on_stop(func: ListenerFunc) -> ListenerFunc:
    """Register function as stop event handler."""
    setattr(func, "_listener_event", "stop")
    return func


def on_stopped(func: ListenerFunc) -> ListenerFunc:
    """Register function as stopped event handler."""
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
    event: str
    func: ListenerFunc
    module: Any
    priority: int
    filters: Optional[ptb_filters.BaseFilter]
    commands: tuple[str, ...]
    description: Optional[str]
    usage: Optional[str]

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
        self.event = event
        self.func = func
        self.module = module
        self.priority = priority
        self.filters = filters
        self.commands = commands
        self.description = description
        self.usage = usage

    def __lt__(self, other: "Listener") -> bool:
        return self.priority < other.priority

    def __repr__(self) -> str:
        cmds = f" commands={self.commands}" if self.commands else ""
        return f"<Listener event={self.event} module={self.module.name}{cmds} prio={self.priority}>"
