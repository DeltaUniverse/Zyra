import asyncio
import datetime
import signal
from functools import partial
from typing import Any

from telegram import Bot, LinkPreviewOptions, Update, User
from telegram.constants import UpdateType
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

from .bus import EventBus
from .events import Events


class TelegramInterface:
    def __init__(
        self,
        token: str,
        event_bus: EventBus,
        owner_id: int,
        log: Any,
        base_url: str = None,
    ):
        self.token = token
        self.base_url = base_url
        self.event_bus = event_bus
        self.owner_id = owner_id
        self.log = log

        self.application: Application = None
        self.client: Bot = None
        self.me: User = None
        self.bot_username: str = None
        self.sudoers: set[int] = set()
        self._handlers: dict[str, tuple[Any, int]] = {}
        self._idle_task: asyncio.Task = None

    async def initialize(self, db_pool: Any) -> None:
        builder = (
            ApplicationBuilder()
            .token(self.token)
            .defaults(
                Defaults(
                    parse_mode="HTML",
                    disable_notification=True,
                    tzinfo=datetime.timezone(datetime.timedelta(hours=7)),
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            )
        )

        if self.base_url:
            builder.base_url(f"{self.base_url}/bot{{token}}")
            builder.base_file_url(f"{self.base_url}/file/bot{{token}}")
            builder.local_mode(True)
            builder.http_version("1.1")
            builder.get_updates_http_version("1.1")
            self.log.info(f"Using local Bot API server: {self.base_url}")

        self.application = builder.build()
        self.client = self.application.bot

        try:
            rows = await db_pool.fetch("SELECT id FROM users WHERE rank = 'sudoer'")
            self.sudoers = {int(r["id"]) for r in rows}
        except Exception as e:
            self.log.warning(f"Skipping sudoers load: {e}")

        await self.application.initialize()

    def bind_handlers(self) -> None:
        msg_filter = (
            filters.ALL
            & ~filters.StatusUpdate.NEW_CHAT_MEMBERS
            & ~filters.StatusUpdate.LEFT_CHAT_MEMBER
            & ~filters.StatusUpdate.MIGRATE
        )
        self._bind_event(
            Events.MESSAGE.value, MessageHandler(msg_filter, self._on_message), group=0
        )

        chat_action_filter = (
            filters.StatusUpdate.NEW_CHAT_MEMBERS
            | filters.StatusUpdate.LEFT_CHAT_MEMBER
            | filters.StatusUpdate.MIGRATE
        )
        self._bind_event(
            Events.CHAT_ACTION.value,
            MessageHandler(chat_action_filter, self._on_message),
            group=1,
        )

        self._bind_event(
            Events.CALLBACK_QUERY.value,
            CallbackQueryHandler(self._on_callback),
            group=0,
        )
        self._bind_event(
            Events.INLINE_QUERY.value, InlineQueryHandler(self._on_inline), group=0
        )
        self._bind_event(
            Events.CHOSEN_INLINE_RESULT.value,
            ChosenInlineResultHandler(self._on_chosen),
            group=0,
        )

    def _bind_event(self, name: str, handler: Any, group: int = 0) -> None:
        if name not in self._handlers:
            self.application.add_handler(handler, group=group)
            self._handlers[name] = (handler, group)

    async def _on_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.event_bus.dispatch(Events.MESSAGE, update, context)

    async def _on_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.event_bus.dispatch(Events.CALLBACK_QUERY, update, context)

    async def _on_inline(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.event_bus.dispatch(Events.INLINE_QUERY, update, context)

    async def _on_chosen(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self.event_bus.dispatch(Events.CHOSEN_INLINE_RESULT, update, context)

    async def start(self) -> None:
        self.me = await self.client.get_me()
        self.bot_username = self.me.username
        await self.application.start()
        await self.application.updater.start_polling(
            allowed_updates=[
                UpdateType.MESSAGE,
                UpdateType.CALLBACK_QUERY,
                UpdateType.INLINE_QUERY,
                UpdateType.CHOSEN_INLINE_RESULT,
            ],
            drop_pending_updates=True,
        )

    async def stop(self) -> None:
        await asyncio.gather(
            self.application.stop(),
            self.application.updater.stop(),
            return_exceptions=True,
        )

    async def idle(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._idle_task:
            raise RuntimeError("Already running")

        signal_names = {
            k: v
            for v, k in signal.__dict__.items()
            if v.startswith("SIG") and not v.startswith("SIG_")
        }

        def clear_handlers():
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass

        def on_signal(signum):
            print(flush=True)
            name = signal_names.get(signum, str(signum))
            self.log.info(f"Stop signal received ('{name}')")
            clear_handlers()
            if self._idle_task:
                self._idle_task.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
            try:
                loop.add_signal_handler(sig, partial(on_signal, sig))
            except (NotImplementedError, RuntimeError):
                pass

        while True:
            self._idle_task = asyncio.create_task(asyncio.sleep(300))
            try:
                await self._idle_task
            except asyncio.CancelledError:
                break
