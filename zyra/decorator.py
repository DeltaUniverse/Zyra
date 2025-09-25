from typing import Any, Awaitable, Callable, Iterable

from telegram import Update

ContextFunc = Callable[..., Awaitable[Any]]
Predicate = Callable[[Any], bool | Awaitable[bool]]

__all__ = [
    "filters",
    "filters_all",
    "filters_any",
    "desc",
    "aliases",
    "priority",
    "command",
    "iq_prefix",
    "iq_exact",
    "iq_minlen",
    "cq_data_prefix",
    "cq_from_user",
    "cir_result_id_prefix",
    "msg_text_prefix",
]


def filters(flt: Any) -> Callable[[ContextFunc], ContextFunc]:
    """
    Attach a filter to a handler function.

    The filter can be:
      • A PTB-style filter object (with .check_update)
      • A callable that accepts the event context (or Update)
      • A list/tuple of filters to AND together (handled by the dispatcher)

    Returns the original function with metadata attached.
    """

    def _wrap(fn: ContextFunc) -> ContextFunc:
        setattr(fn, "_listener_filters", flt)
        return fn

    return _wrap


def filters_all(*flts: Any) -> Callable[[ContextFunc], ContextFunc]:
    """
    Attach multiple filters that must all pass (logical AND).

    The dispatcher treats sequences as an AND group. Use this helper
    when stacking many filters to keep module code readable.
    """
    items = list(flts)

    def _as_list(_: Any) -> list[Any]:
        return items

    return filters(_as_list)


def filters_any(*flts: Any) -> Callable[[ContextFunc], ContextFunc]:
    """
    Attach a composite filter that passes if any filter passes (logical OR).

    This wraps multiple filters into a single callable that returns True
    as soon as one sub-filter evaluates to truthy.
    """
    items = list(flts)

    def _any(subject: Any) -> bool:
        for f in items:
            if callable(f) and not hasattr(f, "check_update"):
                res = f(subject)
                return (
                    True
                    if (res if not hasattr(res, "__await__") else False)
                    else False or bool(res)
                )  # noqa: E701

            if hasattr(f, "check_update"):
                upd = (
                    subject
                    if isinstance(subject, Update)
                    else getattr(subject, "update", subject)
                )
                res = f.check_update(upd)
                if not hasattr(res, "__await__") and res:
                    return True

            if f:
                return True

        return False

    return filters(_any)


def desc(text: str) -> Callable[[ContextFunc], ContextFunc]:
    """
    Set a short human-readable description for the handler.

    Useful for help menus and auto-generated documentation.
    """

    def _wrap(fn: ContextFunc) -> ContextFunc:
        setattr(fn, "_listener_desc", text)
        return fn

    return _wrap


def aliases(*names: str | Iterable[str]) -> Callable[[ContextFunc], ContextFunc]:
    """
    Declare command aliases for the handler.

    Accepts varargs or a single iterable: aliases("ping", "p") or aliases(["ping", "p"]).
    """
    if len(names) == 1 and isinstance(names[0], (list, tuple, set)):
        names = tuple(names[0])  # type: ignore[assignment]

    items = tuple(str(n) for n in names)  # type: ignore[arg-type]

    def _wrap(fn: ContextFunc) -> ContextFunc:
        setattr(fn, "_listener_aliases", items)
        return fn

    return _wrap


def priority(value: int) -> Callable[[ContextFunc], ContextFunc]:
    """
    Set dispatch priority for the handler (lower runs first when sorted ascending).

    Default priority is 100. Tune to order handlers within the same event.
    """

    def _wrap(fn: ContextFunc) -> ContextFunc:
        setattr(fn, "_listener_priority", int(value))
        return fn

    return _wrap


def command(*names: str | Iterable[str]) -> Callable[[ContextFunc], ContextFunc]:
    """
    Declare a command handler with given names and an invoker-aware filter.

    This attaches aliases and a predicate that checks ctx.invoker (or infers from Update)
    so the dispatcher can route commands without extra boilerplate.
    """
    if len(names) == 1 and isinstance(names[0], (list, tuple, set)):
        vals = tuple(str(x) for x in names[0])  # type: ignore[arg-type]
    else:
        vals = tuple(str(x) for x in names)  # type: ignore[arg-type]

    def _check(subject: Any) -> bool:
        inv = getattr(subject, "invoker", None)
        if inv is None:
            upd = getattr(subject, "update", subject)
            msg = getattr(getattr(upd, "effective_message", None), "text", "") or ""
            head = msg.split(maxsplit=1)[0] if msg else ""
            inv = head.lstrip("/").split("@", 1)[0] if head else None

        return inv in vals if inv else False

    def _wrap(fn: ContextFunc) -> ContextFunc:
        setattr(fn, "_listener_aliases", vals)
        setattr(fn, "_listener_filters", _check)
        return fn

    return _wrap


def iq_prefix(*prefixes: str) -> Callable[[ContextFunc], ContextFunc]:
    """
    Filter inline queries by prefix.

    Pass one or more string prefixes; matches when query.text starts with any of them.
    """

    def _check(ctx: Any) -> bool:
        q = getattr(getattr(ctx, "query", None), "query", "") or ""
        return any(q.startswith(p) for p in prefixes)

    return filters(_check)


def iq_exact(*values: str) -> Callable[[ContextFunc], ContextFunc]:
    """
    Filter inline queries by exact text match.

    Useful for discrete command-like inline queries.
    """

    def _check(ctx: Any) -> bool:
        q = getattr(getattr(ctx, "query", None), "query", "") or ""
        return q in values

    return filters(_check)


def iq_minlen(n: int) -> Callable[[ContextFunc], ContextFunc]:
    """
    Filter inline queries by minimum length.

    Helpful to avoid premature processing or rate-heavy lookups on short inputs.
    """

    def _check(ctx: Any) -> bool:
        q = getattr(getattr(ctx, "query", None), "query", "") or ""
        return len(q) >= n

    return filters(_check)


def cq_data_prefix(*prefixes: str) -> Callable[[ContextFunc], ContextFunc]:
    """
    Filter callback queries by data prefix.

    Matches when CallbackQuery.data starts with any of the given prefixes.
    """

    def _check(ctx: Any) -> bool:
        data = getattr(getattr(ctx, "query", None), "data", "") or ""
        return any(data.startswith(p) for p in prefixes)

    return filters(_check)


def cq_from_user(*user_ids: int) -> Callable[[ContextFunc], ContextFunc]:
    """
    Filter callback queries by originating user id(s).

    Accepts one or more user IDs. Useful for owner-only buttons.
    """
    allow = set(int(x) for x in user_ids)

    def _check(ctx: Any) -> bool:
        uid = getattr(
            getattr(getattr(ctx, "query", None), "from_user", None), "id", None
        )
        return uid in allow

    return filters(_check)


def cir_result_id_prefix(*prefixes: str) -> Callable[[ContextFunc], ContextFunc]:
    """
    Filter chosen inline results by result_id prefix.

    Handy for routing results from different inline providers in one handler.
    """

    def _check(ctx: Any) -> bool:
        rid = getattr(getattr(ctx, "result", None), "result_id", "") or ""
        return any(rid.startswith(p) for p in prefixes)

    return filters(_check)


def msg_text_prefix(*prefixes: str) -> Callable[[ContextFunc], ContextFunc]:
    """
    Filter messages by text/caption prefix.

    Works for both text and media captions. Useful for lightweight, non-command triggers.
    """

    def _check(ctx: Any) -> bool:
        msg = getattr(ctx, "message", None)
        s = getattr(msg, "text", None) or getattr(msg, "caption", "") or ""
        return any(s.startswith(p) for p in prefixes)

    return filters(_check)
