from typing import Callable, Sequence

from .core.events import Events, Hooks


def handler(
    event: str | Sequence[str] | Events,
    *,
    filters: Callable = None,
    priority: int = 100,
) -> Callable:
    def wrap(fn: Callable) -> Callable:
        if isinstance(event, (list, tuple, set)):
            setattr(fn, "_evt", Events.COMMAND.value)
            setattr(fn, "_cmds", tuple(event))
            setattr(fn, "_flt", filters)
            setattr(fn, "_prio", priority)
            return fn

        ev = event.value if isinstance(event, Events) else str(event).strip().lower()

        if ev == "start":
            setattr(fn, "_evt", Events.COMMAND.value)
            setattr(fn, "_cmds", ("start",))
            setattr(fn, "_flt", filters)
            setattr(fn, "_prio", priority)
            return fn

        if ev in {h.value for h in Hooks}:
            raise ValueError("Hooks must be defined as on_<hook>() without decorators")

        setattr(fn, "_evt", ev)
        setattr(fn, "_flt", filters)
        setattr(fn, "_prio", priority)
        return fn

    return wrap


def owner_only(update, context, bot):
    user = getattr(update, "effective_user", None)
    return user and user.id == bot.owner_id


def sudo_only(update, context, bot):
    user = getattr(update, "effective_user", None)
    if not user:
        return False

    return user.id == bot.owner_id or user.id in bot.sudoers


def rank_filter(rank: str):
    def check(update, context, bot):
        user = getattr(update, "effective_user", None)
        if not user:
            return False

        r = rank.strip().lower()
        if r == "owner":
            return user.id == bot.owner_id

        if r == "sudo":
            return user.id == bot.owner_id or user.id in bot.sudoers

        if r == "nobody":
            return False

        return False

    return check


def parse_callback(data: str, prefix: str) -> list[str]:
    if not data or not data.startswith(f"{prefix}:"):
        return []

    return data.split(":")[1:]
