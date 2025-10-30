import inspect
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
    self: Optional["Zyra"] = field(default=None, compare=False)

    async def check(self, update, context) -> bool:
        flt = self.filters
        if flt is None:
            return True

        async def _eval(f) -> bool:
            if isinstance(f, (list, tuple, set)):
                for sub in f:
                    if not await _eval(sub):
                        return False

                return True

            if callable(f):
                try:
                    res = f(update, context, self.self)
                except TypeError:
                    res = f(update, context)

                if inspect.isawaitable(res):
                    res = await res

                if isinstance(res, (list, tuple, set)):
                    return await _eval(res)

                return bool(res)

            return bool(f)

        return await _eval(flt)


def handler(
    event: Union[str, Sequence[str]],
    *,
    filters: Optional[Filter] = None,
    priority: int = 100,
) -> Callable[[Func], Func]:
    def wrap(fn: Func) -> Func:
        if isinstance(event, (list, tuple, set)):
            setattr(fn, "_evt", "command")
            setattr(fn, "_cmds", tuple(event))
            setattr(fn, "_flt", filters)
            setattr(fn, "_prio", priority)
            return fn

        ev = str(event)
        if ev in _HOOKS:
            raise ValueError("Hooks must be defined as on_<hook>() without decorators")

        setattr(fn, "_evt", ev)
        setattr(fn, "_flt", filters)
        setattr(fn, "_prio", priority)
        return fn

    return wrap


def rank_limit(rank: str | None = None):
    def _check(update, context, self):
        u = getattr(update, "effective_user", None)
        if not u:
            return False

        r = (rank or "").strip().lower()
        if not r:
            return True

        if r == "owner":
            return u.id == getattr(self, "owner_id", None)

        if r == "sudo":
            owner_id = getattr(self, "owner_id", None)
            sudoers = getattr(self, "sudoers", set())
            return u.id == owner_id or u.id in sudoers

        if r == "nobody":
            return False

        return False

    return _check
