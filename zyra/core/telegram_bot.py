import asyncio
import datetime
import signal
from functools import partial
from typing import TYPE_CHECKING, Any, List, Tuple, Union

from telegram import (
    Bot,
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    LinkPreviewOptions,
    Message,
    Update,
    User,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    ContextTypes,
    Defaults,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from ..util import time
from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra

Handler = Union[
    CallbackQueryHandler, InlineQueryHandler, MessageHandler, ChosenInlineResultHandler
]
Event = Union[CallbackQuery, InlineQuery, List[Message], Message, ChosenInlineResult]
ALLOWED_EVENT: list[str] = [
    "message",
    "callback_query",
    "inline_query",
    "chosen_inline_result",
]


class TelegramBot(ZyraBase):
    """Telegram bot bridge using python-telegram-bot v22."""

    application: Application
    client: Bot
    owner_id: int
    prefix: str
    user: User
    start_time_us: int
    _handlers: dict[str, Tuple[Handler, int]]
    __idle__: asyncio.Task[None]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        """Initialize with app state and config bindings."""
        self.loaded = False
        self._handlers = {}
        self.__idle__ = None  # type: ignore
        super().__init__(**kwargs)

    async def init_client(self: "Zyra") -> None:
        """Create Application, bot client, and baseline handlers."""
        token = self.config["telegram"]["token"]
        self.application = (
            ApplicationBuilder()
            .token(token)
            .defaults(
                Defaults(
                    parse_mode="HTML",
                    disable_notification=True,
                    tzinfo=datetime.timezone(datetime.timedelta(hours=7)),
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            )
            .build()
        )
        self.client = self.application.bot
        self.prefix = self.config["bot"]["prefix"]
        self.owner_id = self.config["rank"]["owner_id"]
        self.update_module_events()

    async def start(self: "Zyra") -> None:
        """Start polling and dispatch lifecycle events."""
        self.log.info("Starting")
        await self.init_client()
        self.load_all_modules()
        await self.dispatch_event("load")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=ALLOWED_EVENT)
        self.loaded = True
        self.user = await self.application.bot.get_me()
        self.start_time_us = time.usec()
        await self.dispatch_event("start", self.start_time_us)
        self.log.info("Bot is ready")
        await self.dispatch_event("started")

    async def idle(self: "Zyra") -> None:
        """Sleep-loop until a termination signal is received."""
        if self.__idle__:
            raise RuntimeError("This bot instance is already running")
        signal_names: dict[Any, str] = {}
        for k, _ in signal.__dict__.items():
            if isinstance(k, str) and k.startswith("SIG") and not k.startswith("SIG_"):
                try:
                    sig = getattr(signal, k)
                except Exception:
                    continue
                if isinstance(sig, (int, getattr(signal, "Signals", int))):
                    signal_names[sig] = k

        def clear_handler() -> None:
            for sig in (
                getattr(signal, "SIGINT", None),
                getattr(signal, "SIGTERM", None),
                getattr(signal, "SIGABRT", None),
            ):
                if sig is None:
                    continue
                try:
                    self.loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass

        def signal_handler(signum) -> None:
            print(flush=True)
            name = signal_names.get(signum, getattr(signum, "name", str(signum)))
            self.log.info("Stop signal received ('%s').", name)
            clear_handler()
            if self.__idle__:
                self.__idle__.cancel()

        for sig in (
            getattr(signal, "SIGINT", None),
            getattr(signal, "SIGTERM", None),
            getattr(signal, "SIGABRT", None),
        ):
            if sig is None:
                continue
            try:
                self.loop.add_signal_handler(sig, partial(signal_handler, sig))
            except (NotImplementedError, RuntimeError):
                pass

        while True:
            self.__idle__ = asyncio.create_task(asyncio.sleep(300), name="idle")
            try:
                await self.__idle__
            except asyncio.CancelledError:
                break

    async def run(self: "Zyra") -> None:
        """Run until stopped."""
        if self.__idle__:
            raise RuntimeError("This bot instance is already running")
        try:
            try:
                await self.start()
            except KeyboardInterrupt:
                self.log.warning("Received interrupt while connecting")
                return
            except TelegramError as e:
                self.log.exception("Telegram error on startup", exc_info=e)
                return
            await self.idle()
        finally:
            await self.stop()

    def _bind_event(self: "Zyra", name: str, handler: Handler, group: int = 0) -> None:
        """Bind or unbind a PTB handler based on active listeners."""
        if name in self.listeners:
            if name not in self._handlers:
                self.application.add_handler(handler, group=group)
                self._handlers[name] = (handler, group)
        elif name in self._handlers:
            h, g = self._handlers.pop(name)
            self.application.remove_handler(h, group=g)

    def update_module_events(self: "Zyra") -> None:
        """Register handlers according to active listener sets."""
        msg_filter = (
            filters.ALL
            & ~filters.StatusUpdate.NEW_CHAT_MEMBERS
            & ~filters.StatusUpdate.LEFT_CHAT_MEMBER
            & ~filters.StatusUpdate.MIGRATE
        )
        self._bind_event(
            "message", MessageHandler(msg_filter, self._evt_message), group=0
        )

        chat_action_filter = (
            filters.StatusUpdate.NEW_CHAT_MEMBERS
            | filters.StatusUpdate.LEFT_CHAT_MEMBER
            | filters.StatusUpdate.MIGRATE
        )
        self._bind_event(
            "chat_action",
            MessageHandler(chat_action_filter, self._evt_message),
            group=1,
        )

        self._bind_event(
            "callback_query", CallbackQueryHandler(self._evt_callback), group=0
        )
        self._bind_event("inline_query", InlineQueryHandler(self._evt_inline), group=0)
        self._bind_event(
            "chosen_inline_result", ChosenInlineResultHandler(self._evt_chosen), group=0
        )

    async def _evt_message(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Forward message updates."""
        if update.effective_message:
            await self.dispatch_event("message", update, context)

    async def _evt_callback(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Forward callback_query updates."""
        if update.callback_query:
            await self.dispatch_event("callback_query", update, context)

    async def _evt_inline(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Forward inline_query updates."""
        if update.inline_query:
            await self.dispatch_event("inline_query", update, context)

    async def _evt_chosen(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Forward chosen_inline_result updates."""
        if update.chosen_inline_result:
            await self.dispatch_event("chosen_inline_result", update, context)

    @property
    def events_activated(self: "Zyra") -> int:
        """Return the number of active PTB handlers."""
        return len(self._handlers)

    def redact_message(self: "Zyra", text: str) -> str:
        """Redact sensitive tokens from text."""
        redacted = "[REDACTED]"
        bot_token = self.config["telegram"].get("token")
        if bot_token and bot_token in text:
            text = text.replace(bot_token, redacted)
        return text
