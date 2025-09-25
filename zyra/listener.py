from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, Sequence

from telegram import (
    CallbackQuery,
    Chat,
    ChosenInlineResult,
    InlineQuery,
    Message,
    Update,
)

from . import decorator as _dec

if TYPE_CHECKING:
    from .bot import Zyra
    from .module import Module as _Module

ContextFunc = Callable[..., Awaitable[Any]]

filters = _dec.filters
filters_all = _dec.filters_all
filters_any = _dec.filters_any
desc = _dec.desc
aliases = _dec.aliases
priority = _dec.priority
command = _dec.command
iq_prefix = _dec.iq_prefix
iq_exact = _dec.iq_exact
iq_minlen = _dec.iq_minlen
cq_data_prefix = _dec.cq_data_prefix
cq_from_user = _dec.cq_from_user
cir_result_id_prefix = _dec.cir_result_id_prefix
msg_text_prefix = _dec.msg_text_prefix

__all__ = [
    "Listener",
    "Context",
    "CallbackQueryContext",
    "InlineQueryContext",
    "ChosenInlineResultContext",
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


@dataclass(order=True)
class Listener:
    priority: int
    event: str = field(compare=False)
    func: ContextFunc = field(compare=False)
    module: "_Module" = field(compare=False)
    filter: Any = field(default=None, compare=False)


class Context:
    def __init__(
        self,
        *,
        bot: "Zyra",
        chat: Optional[Chat],
        message: Optional[Message],
        cmd_len: int,
        segments: Sequence[str],
        update: Update,
        raw_context: Any,
        last_update_time: Optional[float],
    ) -> None:
        self.bot = bot
        self.chat = chat
        self.message = message
        self.cmd_len = cmd_len
        self.segments = list(segments)
        self.update = update
        self.raw_context = raw_context
        self.last_update_time = last_update_time
        self.invoker = segments[0] if segments else None

    @property
    def text(self) -> str:
        if self.message:
            return (self.message.text or self.message.caption or "") or ""

        return ""

    @property
    def args(self) -> list[str]:
        if not self.segments:
            return []

        return list(self.segments[1:])

    async def reply(self, text: str, **kwargs: Any) -> Any:
        if self.message:
            return await self.message.reply_text(text, **kwargs)

        return None


class CallbackQueryContext:
    def __init__(
        self,
        *,
        bot: "Zyra",
        query: CallbackQuery,
        update: Update,
        raw_context: Any,
        last_update_time: Optional[float],
    ) -> None:
        self.bot = bot
        self.query = query
        self.update = update
        self.raw_context = raw_context
        self.last_update_time = last_update_time

    async def answer(self, text: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.query.answer(text=text, **kwargs)


class InlineQueryContext:
    def __init__(
        self,
        *,
        bot: "Zyra",
        query: InlineQuery,
        update: Update,
        raw_context: Any,
        last_update_time: Optional[float],
    ) -> None:
        self.bot = bot
        self.query = query
        self.update = update
        self.raw_context = raw_context
        self.last_update_time = last_update_time


class ChosenInlineResultContext:
    def __init__(
        self,
        *,
        bot: "Zyra",
        result: ChosenInlineResult,
        update: Update,
        raw_context: Any,
        last_update_time: Optional[float],
    ) -> None:
        self.bot = bot
        self.result = result
        self.update = update
        self.raw_context = raw_context
        self.last_update_time = last_update_time
