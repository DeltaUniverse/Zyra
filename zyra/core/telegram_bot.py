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
from telegram.constants import UpdateType
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

from ..util import error, time
from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra

Handler = Union[
    CallbackQueryHandler, InlineQueryHandler, MessageHandler, ChosenInlineResultHandler
]
Event = Union[CallbackQuery, InlineQuery, List[Message], Message, ChosenInlineResult]
EVENT_TYPES: list[UpdateType] = [
    Update.MESSAGE,
    Update.CALLBACK_QUERY,
    Update.INLINE_QUERY,
    Update.CHOSEN_INLINE_RESULT,
]


class TelegramBot(ZyraBase):

    application: Application
    client: Bot
    me: User

    owner_id: int
    sudoers: set[int]
    start_time_us: int
    _handlers: dict[str, Tuple[Handler, int]]
    __idle__: asyncio.Task[None]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.loaded = False
        self._handlers = {}
        self.__idle__ = None
        self.sudoers = set()
        super().__init__(**kwargs)

    async def init_client(self: "Zyra") -> None:
        token = self.config["telegram"]["token"]
        base_url: str | None = self.config["telegram"].get("base_url")
        builder = (
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
        )
        if base_url:
            builder.base_url(f"{base_url}/bot{{token}}")
            builder.base_file_url(f"{base_url}/file/bot{{token}}")
            builder.local_mode(True)
            builder.http_version("1.1")
            builder.get_updates_http_version("1.1")
            self.log.info("Using local Bot API server: %s", base_url)

        self.application = builder.build()
        self.client = self.application.bot
        self.owner_id = self.config["rank"]["owner_id"]
        sudo = await self.db.fetch("SELECT id FROM users WHERE rank = 'sudoer';")
        self.sudoers = {int(r["id"]) for r in sudo}
        self.application.add_error_handler(
            error.make_error_handler(
                self.owner_id, logger=self.log, redact=self.redact_message
            )
        )
        await self.application.initialize()

    async def start(self: "Zyra") -> None:
        self.log.info("Starting")
        await self.init_client()
        self.load_all_modules()
        await self.dispatch_event("load")
        self.loaded = True

        await self.application.start()
        await self.application.updater.start_polling(
            allowed_updates=EVENT_TYPES, drop_pending_updates=True
        )

        self.me = await self.application.bot.get_me()
        self.bot_username = self.me.username
        self.start_time_us = time.usec()
        await self.dispatch_event("start", self.start_time_us)
        self.log.info("Bot is ready")
        await self.dispatch_event("started")

    async def idle(self: "Zyra") -> None:
        if self.__idle__:
            raise RuntimeError("This bot instance is already running")

        signal_names: dict[Any, str] = {
            k: v
            for v, k in signal.__dict__.items()
            if v.startswith("SIG") and not v.startswith("SIG_")
        }

        def clear_handler() -> None:
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
                try:
                    self.loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass

        def signal_handler(signum) -> None:
            print(flush=True)
            name = signal_names.get(signum, str(signum))
            self.log.info("Stop signal received ('%s').", name)
            clear_handler()
            if self.__idle__:
                self.__idle__.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
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

    def _bind_event(
        self: "Zyra",
        name: str,
        handler: Handler,
        group: int = 0,
        *,
        force: bool = False,
    ) -> None:
        if force or name in self.listeners:
            if name not in self._handlers:
                self.application.add_handler(handler, group=group)
                self._handlers[name] = (handler, group)
        elif name in self._handlers:
            h, g = self._handlers.pop(name)
            self.application.remove_handler(h, group=g)

    def update_module_events(self: "Zyra") -> None:
        msg_filter = (
            filters.ALL
            & ~filters.StatusUpdate.NEW_CHAT_MEMBERS
            & ~filters.StatusUpdate.LEFT_CHAT_MEMBER
            & ~filters.StatusUpdate.MIGRATE
        )
        self._bind_event(
            "message",
            MessageHandler(msg_filter, self._evt_message),
            group=0,
            force=True,
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
            force=True,
        )

        self._bind_event(
            "callback_query",
            CallbackQueryHandler(self._evt_callback),
            group=0,
            force=True,
        )
        self._bind_event(
            "inline_query", InlineQueryHandler(self._evt_inline), group=0, force=True
        )
        self._bind_event(
            "chosen_inline_result",
            ChosenInlineResultHandler(self._evt_chosen),
            group=0,
            force=True,
        )

    async def _evt_message(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.dispatch_event("message", update, context)

    async def _evt_callback(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.dispatch_event("callback_query", update, context)

    async def _evt_inline(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.dispatch_event("inline_query", update, context)

    async def _evt_chosen(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.dispatch_event("chosen_inline_result", update, context)

    @property
    def events_activated(self: "Zyra") -> int:
        return len(self._handlers)

    def redact_message(self: "Zyra", text: str) -> str:
        bot_token = self.config["telegram"].get("token")
        if bot_token and bot_token in text:
            return text.replace(bot_token, "[REDACTED]")

        return text
