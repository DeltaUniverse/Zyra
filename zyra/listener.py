# zyra/listener.py
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Sequence

from telegram import (
    CallbackQuery,
    Chat,
    ChosenInlineResult,
    InlineQuery,
    Message,
    Update,
)
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from .core import Zyra


class BaseContext:
    """Base context class with common functionality"""

    def __init__(
        self,
        bot: "Zyra",
        update: Update,
        raw_context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        last_update_time: Optional[datetime] = None,
    ) -> None:
        self.bot = bot
        self.update = update
        self.raw_context = raw_context  # Original PTB context
        self.last_update_time = last_update_time

    @property
    def user(self):
        """Get the user from the update"""
        return self.update.effective_user

    @property
    def chat(self):
        """Get the chat from the update"""
        return self.update.effective_chat


class Context(BaseContext):
    """Message/Command context - your existing implementation enhanced"""

    def __init__(
        self,
        bot: "Zyra",
        chat: Chat,
        message: Message,
        cmd_len: int,
        *,
        segments: Sequence[str],
        update: Update,
        raw_context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        last_update_time: Optional[datetime] = None,
    ) -> None:
        super().__init__(bot, update, raw_context, last_update_time)
        self.msg = message
        self.message = message
        self.reply_msg = message.reply_to_message
        self.segments = list(segments)
        self.cmd_len = cmd_len
        self.invoker = self.segments[0] if self.segments else ""
        self.input = (self.msg.text or "")[self.cmd_len :]

    def __getattr__(self, name: str) -> Any:
        if name == "args":
            return self._get_args()

        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def _get_args(self) -> Sequence[str]:
        self.args = self.segments[1:]
        return self.args

    async def respond(self, text: str, **kwargs) -> Message:
        if "do_quote" not in kwargs:
            kwargs["do_quote"] = True

        return await self.msg.reply_text(text, **kwargs)

    async def reply(self, text: str, **kwargs) -> Message:
        return await self.respond(text, **kwargs)


class CallbackQueryContext(BaseContext):
    """Context for callback query events"""

    def __init__(
        self,
        bot: "Zyra",
        query: CallbackQuery,
        update: Update,
        raw_context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        last_update_time: Optional[datetime] = None,
    ) -> None:
        super().__init__(bot, update, raw_context, last_update_time)
        self.query = query
        self.data = query.data
        self.message = query.message
        self.msg = query.message  # Alias for consistency

    async def answer(self, text: str = None, show_alert: bool = False, **kwargs):
        """Answer the callback query"""
        return await self.query.answer(text=text, show_alert=show_alert, **kwargs)

    async def edit_message_text(self, text: str, **kwargs):
        """Edit the message text"""
        if self.message:
            return await self.message.edit_text(text, **kwargs)

        return None

    async def edit_message_reply_markup(self, reply_markup=None, **kwargs):
        """Edit the message reply markup"""
        if self.message:
            return await self.message.edit_reply_markup(
                reply_markup=reply_markup, **kwargs
            )

        return None


class InlineQueryContext(BaseContext):
    """Context for inline query events"""

    def __init__(
        self,
        bot: "Zyra",
        query: InlineQuery,
        update: Update,
        raw_context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        last_update_time: Optional[datetime] = None,
    ) -> None:
        super().__init__(bot, update, raw_context, last_update_time)
        self.query = query
        self.query_text = query.query
        self.offset = query.offset

    async def answer(self, results, **kwargs):
        """Answer the inline query"""
        return await self.query.answer(results, **kwargs)


class ChosenInlineResultContext(BaseContext):
    """Context for chosen inline result events"""

    def __init__(
        self,
        bot: "Zyra",
        result: ChosenInlineResult,
        update: Update,
        raw_context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        last_update_time: Optional[datetime] = None,
    ) -> None:
        super().__init__(bot, update, raw_context, last_update_time)
        self.result = result
        self.result_id = result.result_id
        self.query_text = result.query


class Listener:
    def __init__(
        self,
        event: str,
        func: Any,
        module: Any,
        priority: int = 100,
        flt: Optional[Any] = None,
    ) -> None:
        self.event = event
        self.func = func
        self.module = module
        self.priority = priority
        self.filter = flt

    def __lt__(self, other: "Listener") -> bool:
        return self.priority < other.priority

    def __repr__(self) -> str:
        return f"<Listener event={self.event} module={getattr(self.module, 'name', self.module.__class__.__name__)} prio={self.priority}>"
