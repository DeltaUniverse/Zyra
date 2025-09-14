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


def filters(_filters: Optional[ptb_filters.BaseFilter]) -> Decorator:
    """Attach a PTB BaseFilter to a listener function."""

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_filters", _filters)
        return func

    return _decorator


class Listener:
    event: str
    func: ListenerFunc
    module: Any
    priority: int
    filters: Optional[ptb_filters.BaseFilter]

    def __init__(
        self,
        event: str,
        func: ListenerFunc,
        mod: Any,
        prio: int,
        listener_filter: Optional[ptb_filters.BaseFilter],
    ) -> None:
        self.event = event
        self.func = func
        self.module = mod
        self.priority = prio
        self.filters = listener_filter

    def __lt__(self, other: "Listener") -> bool:
        return self.priority < other.priority

    def __repr__(self) -> str:
        return f"<listener '{self.event}' from '{self.module.name}'>"
