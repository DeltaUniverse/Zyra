import asyncio
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Iterable,
    Optional,
    Sequence,
    Union,
)

from telegram import Chat, Message
from telegram.ext import CallbackContext, filters

from . import util

if TYPE_CHECKING:
    from .core import Zyra

CommandFunc = Union[
    Callable[..., Coroutine[Any, Any, None]], Callable[..., Coroutine[Any, Any, Any]]
]
Decorator = Callable[[CommandFunc], CommandFunc]


def desc(_desc: str) -> Decorator:
    def _decorator(func: CommandFunc) -> CommandFunc:
        setattr(func, "_cmd_description", _desc)
        return func

    return _decorator


def usage(_usage: str, optional: bool = False, reply: bool = False) -> Decorator:
    def _decorator(func: CommandFunc) -> CommandFunc:
        setattr(func, "_cmd_usage", _usage)
        setattr(func, "_cmd_usage_optional", optional)
        return func

    return _decorator


def alias(*aliases: str) -> Decorator:
    def _decorator(func: CommandFunc) -> CommandFunc:
        setattr(func, "_cmd_aliases", aliases)
        return func

    return _decorator


def filters_dec(_filters: Optional[filters.BaseFilter] = None) -> Decorator:
    """Decorator name kept as `filters` previously; renamed to avoid shadowing."""

    def _decorator(func: CommandFunc) -> CommandFunc:
        setattr(func, "_cmd_filters", _filters)
        return func

    return _decorator


class Command:
    name: str
    desc: Optional[str]
    usage: Optional[str]
    usage_optional: bool
    aliases: Iterable[str]
    filters: Optional[filters.BaseFilter]
    module: Any
    func: CommandFunc

    def __init__(
        self,
        name: str,
        mod: Any,
        func: CommandFunc,
        filters: Optional[filters.BaseFilter] = None,
        desc: Optional[str] = None,
        usage: Optional[str] = None,
        usage_optional: bool = False,
        aliases: Iterable[str] = (),
    ) -> None:
        self.name = name
        self.module = mod
        self.func = func
        self.filters = filters
        self.desc = desc
        self.usage = usage
        self.usage_optional = usage_optional
        self.aliases = aliases

    def __repr__(self) -> str:
        return f"<command module '{self.name}' from '{self.module.name}'>"


class Context:
    bot: "Zyra"
    chat: Chat
    msg: Message
    message: Message
    reply_msg: Optional[Message]
    segments: Sequence[str]
    cmd_len: int
    invoker: str

    last_update_time: Optional[datetime]

    response: Message
    response_mode: Optional[str]

    input: str
    # args provided lazily

    def __init__(
        self,
        bot: "Zyra",
        message: Message,
        cmd_len: int,
        *,
        segments: Sequence[str],
        ptb_context: Optional[CallbackContext] = None,
    ) -> None:
        self.bot = bot
        self.chat = message.chat
        self.msg = message
        self.message = message
        self.reply_msg = message.reply_to_message
        self.segments = segments
        self.cmd_len = cmd_len
        self.invoker = self.segments[0]

        self.last_update_time = None

        self.response = None  # type: ignore
        self.response_mode = None

        self.input = (self.msg.text or "")[self.cmd_len :]

        self.ptb: Optional[CallbackContext] = ptb_context

    def __getattr__(self, name: str) -> Any:
        if name == "args":
            return self._get_args()
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def _get_args(self) -> Sequence[str]:
        if self.ptb is not None and getattr(self.ptb, "args", None) is not None:
            self.args = list(self.ptb.args)  # type: ignore[attr-defined]
            return self.args  # type: ignore[return-value]
        self.args = self.segments[1:]  # type: ignore[attr-defined]
        return self.args  # type: ignore[return-value]

    async def _delete(
        self, delay: Optional[float] = None, message: Optional[Message] = None
    ) -> None:
        content = message or self.response
        if not content:
            return

        async def _do_delete():
            await content.delete()

        if delay:

            async def _delayed(d: float):
                await asyncio.sleep(d)
                await _do_delete()

            self.bot.loop.create_task(_delayed(delay))
        else:
            await _do_delete()

    async def respond(
        self,
        text: str = "",
        *,
        mode: Optional[str] = "edit",
        redact: bool = True,
        msg: Optional[Message] = None,
        reuse_response: bool = True,
        delete_after: Optional[Union[int, float]] = None,
        **kwargs: Any,
    ) -> Message:
        self.response = await self.bot.respond(
            msg or self.msg,
            text,
            input_arg=self.input,
            mode=mode,
            redact=redact,
            response=(
                self.response
                if (reuse_response and mode == self.response_mode)
                else None
            ),
            **kwargs,
        )
        self.response_mode = mode

        if delete_after:
            await self._delete(delete_after)
            self.response = None  # type: ignore

        return self.response  # type: ignore

    async def respond_split(
        self,
        text: str,
        *,
        max_pages: Optional[int] = None,
        redact: Optional[bool] = None,
        **kwargs: Any,
    ) -> Message:
        if redact is None:
            redact = self.bot.config["bot"]["redact_responses"]

        if max_pages is None:
            max_pages = self.bot.config["bot"]["overflow_page_limit"]

        if redact:
            text = self.bot.redact_message(text)

        pages_sent = 0
        last_msg: Message = None  # type: ignore
        while text and pages_sent < max_pages:
            if len(text) <= 4096:
                if pages_sent == 0:
                    page = text[: util.tg.MESSAGE_CHAR_LIMIT]
                    ellipsis_chars = 0
                else:
                    page = "..." + text[: util.tg.MESSAGE_CHAR_LIMIT - 3]
                    ellipsis_chars = 3
            elif pages_sent == max_pages - 1:
                if pages_sent == 0:
                    page = text
                    ellipsis_chars = 0
                else:
                    page = "..." + text
                    ellipsis_chars = 3
            else:
                if pages_sent == 0:
                    page = text[: util.tg.MESSAGE_CHAR_LIMIT - 3] + "..."
                    ellipsis_chars = 3
                else:
                    page = "..." + text[: util.tg.MESSAGE_CHAR_LIMIT - 6] + "..."
                    ellipsis_chars = 6

            last_msg = await self.respond_multi(page, **kwargs)
            text = text[util.tg.MESSAGE_CHAR_LIMIT - ellipsis_chars :]
            pages_sent += 1

        return last_msg

    async def respond_multi(
        self,
        *args: Any,
        mode: Optional[str] = None,
        msg: Message = None,  # type: ignore
        reuse_response: bool = False,
        **kwargs: Any,
    ) -> Message:
        if self.response:
            if mode is None:
                mode = "reply"
            if msg is None:
                msg = self.response
            if reuse_response is None:  # type: ignore[truthy-bool]
                reuse_response = False
        return await self.respond(
            *args, mode=mode, msg=msg, reuse_response=reuse_response, **kwargs
        )
