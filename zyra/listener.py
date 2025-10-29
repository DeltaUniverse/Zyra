from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Iterable, Optional, Sequence, Union

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
    commands: Optional[Sequence[str]] = field(default=None, compare=False)


def handler(
    event: str, *, filters: Optional[Filter] = None, priority: int = 100
) -> Callable[[Func], Func]:
    def wrap(fn: Func) -> Func:
        setattr(fn, "_evt", event)
        setattr(fn, "_flt", None if event in _HOOKS else filters)
        setattr(fn, "_prio", priority)
        return fn

    return wrap


def command(
    names: Union[str, Sequence[str], None] = None,
    *,
    filters: Optional[Filter] = None,
    priority: int = 100,
) -> Callable[[Func], Func]:
    cmds = None
    if names is not None:
        cmds = (names,) if isinstance(names, str) else tuple(names)

    def wrap(fn: Func) -> Func:
        setattr(fn, "_evt", "command")
        setattr(fn, "_flt", filters)
        setattr(fn, "_prio", priority)
        if cmds is not None:
            setattr(fn, "_cmds", cmds)

        return fn

    return wrap
