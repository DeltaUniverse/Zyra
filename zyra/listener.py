from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence

from telegram import Message, Update
from telegram.ext import CallbackContext
from telegram.ext import filters as ptb_filters

if TYPE_CHECKING:
    from .core import Zyra

ListenerFunc = Any
Decorator = Callable[[ListenerFunc], ListenerFunc]


class Context:

    def __init__(
        self,
        bot: "Zyra",
        message: Message,
        cmd_len: int,
        *,
        segments: Sequence[str],
        update: Optional[Update] = None,
        _raw_ctx: Optional[CallbackContext] = None,
    ) -> None:
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
        self._raw_ctx = _raw_ctx

    @property
    def args(self) -> Sequence[str]:
        if (
            self._raw_ctx is not None
            and getattr(self._raw_ctx, "args", None) is not None
        ):
            return list(self._raw_ctx.args)

        return self.segments[1:]

    async def respond(self, text: str, **kwargs) -> Message:
        if "do_quote" not in kwargs:
            kwargs["do_quote"] = True

        return await self.msg.reply_text(text, **kwargs)

    async def reply(self, text: str, **kwargs) -> Message:
        return await self.respond(text, **kwargs)


def priority(_prio: int) -> Decorator:

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_priority", _prio)
        return func

    return _decorator


def desc(_desc: str) -> Decorator:

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_description", _desc)
        return func

    return _decorator


def usage(_usage: str) -> Decorator:

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_usage", _usage)
        return func

    return _decorator


def on_message(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "message")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_callback_query(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "callback_query")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_inline_query(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "inline_query")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_chosen_inline_result(
    filters: Optional[ptb_filters.BaseFilter] = None,
) -> Decorator:

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "chosen_inline_result")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_chat_action(filters: Optional[ptb_filters.BaseFilter] = None) -> Decorator:

    def _decorator(func: ListenerFunc) -> ListenerFunc:
        setattr(func, "_listener_event", "chat_action")
        if filters:
            setattr(func, "_listener_filters", filters)

        return func

    return _decorator


def on_load(func: ListenerFunc) -> ListenerFunc:
    setattr(func, "_listener_event", "load")
    return func


def on_start(func: ListenerFunc) -> ListenerFunc:
    setattr(func, "_listener_event", "start")
    return func


def on_started(func: ListenerFunc) -> ListenerFunc:
    setattr(func, "_listener_event", "started")
    return func


def on_stop(func: ListenerFunc) -> ListenerFunc:
    setattr(func, "_listener_event", "stop")
    return func


def on_stopped(func: ListenerFunc) -> ListenerFunc:
    setattr(func, "_listener_event", "stopped")
    return func


def on_commands(
    *commands: str, filters: Optional[ptb_filters.BaseFilter] = None
) -> Decorator:

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
    return on_commands(command, filters=filters)


class Listener:

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
