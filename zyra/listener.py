from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Sequence

from telegram import Chat, Message, Update

if TYPE_CHECKING:
    from .core import Zyra


class Context:
    def __init__(
        self,
        bot: "Zyra",
        chat: Chat,
        message: Message,
        cmd_len: int,
        *,
        segments: Sequence[str],
        update: Update,
        last_update_time: Optional[datetime],
    ) -> None:
        self.bot = bot
        self.chat = message.chat
        self.msg = message
        self.message = message
        self.reply_msg = message.reply_to_message
        self.segments = list(segments)
        self.cmd_len = cmd_len
        self.invoker = self.segments[0] if self.segments else ""
        self.last_update_time = last_update_time
        self.input = (self.msg.text or "")[self.cmd_len :]
        self.update = update

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
