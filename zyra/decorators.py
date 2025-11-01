from typing import Callable, Sequence

from .core.events import Events, Hooks


def handler(
    event: str | Sequence[str] | Events,
    *,
    filters: Callable = None,
    priority: int = 100
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


def requires_owner(update, context, bot):
    user = getattr(update, "effective_user", None)
    if not user:
        return False

    return user.id == bot.owner_id


def requires_sudo(update, context, bot):
    user = getattr(update, "effective_user", None)
    if not user:
        return False

    return user.id == bot.owner_id or user.id in bot.sudoers


def parse_callback_data(data: str, prefix: str) -> list[str] | None:
    if not data:
        return None

    parts = data.split(":")
    return parts[1:] if parts and parts[0] == prefix else None
