from typing import Callable, Sequence

from .core.events import Events, Hooks

HOOK_VALUES = {h.value for h in Hooks}
EVENT_VALUES = {e.value for e in Events}


def handler(
    event: str | Sequence[str] | Events,
    *,
    filters: Callable | None = None,
    priority: int = 100,
) -> Callable:
    evt_value: str
    cmds: tuple[str, ...] | None = None

    if isinstance(event, (list, tuple, set)):
        cmds = tuple(str(x).strip().lower() for x in event)
        evt_value = Events.COMMAND.value
    else:
        if isinstance(event, Events):
            ev = event.value
        else:
            ev = str(event).strip().lower()

        if ev == "start":
            evt_value = Events.COMMAND.value
            cmds = ("start",)
        elif ev in HOOK_VALUES:
            raise ValueError("Hooks must be defined as on_<hook>() without decorators")
        elif ev in EVENT_VALUES:
            evt_value = ev
        else:
            evt_value = Events.COMMAND.value
            cmds = (ev,)

    def wrap(fn: Callable) -> Callable:
        setattr(fn, "_evt", evt_value)
        if cmds is not None:
            setattr(fn, "_cmds", cmds)

        setattr(fn, "_flt", filters)
        setattr(fn, "_prio", priority)
        return fn

    return wrap


def owner_only(update, context, bot):
    user = getattr(update, "effective_user", None)
    return bool(user and user.id == bot.owner_id)


def sudo_only(update, context, bot):
    user = getattr(update, "effective_user", None)
    if not user:
        return False

    return user.id == bot.owner_id or user.id in bot.sudoers


def rank_filter(rank: str):
    r = rank.strip().lower()

    def check(update, context, bot):
        user = getattr(update, "effective_user", None)
        if not user:
            return False

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
