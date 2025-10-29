
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Iterable, Optional, Union

Func = Callable[..., Awaitable[Any]]
Filter = Union[None, Callable[..., Union[bool, Awaitable[bool]]], Iterable[Any]]

class Hooks(str, Enum):
    LOAD = "load"
    START = "start"
    STARTED = "started"
    STOP = "stop"
    STOPPED = "stopped"

_HOOKS = {e.value for e in Hooks}

@dataclass(order=True, slots=True)
class Listener:
    priority: int
    event: str = field(compare=False)
    func: Func = field(compare=False)
    filters: Optional[Filter] = field(default=None, compare=False)

def handler(
    event: str,
    *,
    filters: Optional[Filter] = None,
    priority: int = 100,
) -> Callable[[Func], Func]:
    """Decorator: mark async function as handler for 'event' with optional filters/priority."""
    def wrap(fn: Func) -> Func:
        setattr(fn, "_evt", event)
        setattr(fn, "_flt", None if event in _HOOKS else filters)  # hooks ignore filters
        setattr(fn, "_prio", priority)
        return fn
    return wrap
