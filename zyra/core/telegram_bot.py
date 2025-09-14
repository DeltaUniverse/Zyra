import asyncio
import datetime
import signal
from functools import partial
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, Union

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

from ..util import tg, time
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
    application: Application
    client: Bot
    owner: int
    prefix: str
    user: User
    start_time_us: int
    _handlers: dict[str, Tuple[Handler, int]]
    __idle__: asyncio.Task[None]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.loaded = False
        self._handlers = {}
        self.__idle__ = None  # type: ignore
        super().__init__(**kwargs)

    async def init_client(self: "Zyra") -> None:
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
        self.owner = self.config["rank"]["owner_id"]
        self.update_module_events()

    async def start(self: "Zyra") -> None:
        self.log.info("Starting")
        await self.init_client()
        self.load_all_modules()
        await self.dispatch_event("load")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=ALLOWED_EVENT)
        self.loaded = True

        # Register per-command handlers after Application is running
        self.setup_command_handler(self.application)
        self.user = await self.application.bot.get_me()
        self.start_time_us = time.usec()
        await self.dispatch_event("start", self.start_time_us)
        self.log.info("Bot is ready")
        await self.dispatch_event("started")

    async def idle(self: "Zyra") -> None:
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
        if name in self.listeners:
            if name not in self._handlers:
                self.application.add_handler(handler, group=group)
                self._handlers[name] = (handler, group)
        elif name in self._handlers:
            h, g = self._handlers.pop(name)
            self.application.remove_handler(h, group=g)

    def update_module_events(self: "Zyra") -> None:
        # message (exclude joins/leaves/migrates)
        msg_filter = (
            filters.ALL
            & ~filters.StatusUpdate.NEW_CHAT_MEMBERS
            & ~filters.StatusUpdate.LEFT_CHAT_MEMBER
            & ~filters.StatusUpdate.MIGRATE
        )
        self._bind_event(
            "message", MessageHandler(msg_filter, self._evt_message), group=0
        )

        # chat_action (only joins/leaves/migrates)
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

        # callback / inline / chosen_inline_result
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
        if update.effective_message:
            await self.dispatch_event("message", update.effective_message)

    async def _evt_callback(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if update.callback_query:
            await self.dispatch_event("callback_query", update.callback_query)

    async def _evt_inline(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if update.inline_query:
            await self.dispatch_event("inline_query", update.inline_query)

    async def _evt_chosen(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if update.chosen_inline_result:
            await self.dispatch_event(
                "chosen_inline_result", update.chosen_inline_result
            )

    @property
    def events_activated(self: "Zyra") -> int:
        return len(self._handlers)

    def redact_message(self: "Zyra", text: str) -> str:
        redacted = "[REDACTED]"
        bot_token = self.config["telegram"].get("token")
        if bot_token and bot_token in text:
            text = text.replace(bot_token, redacted)
        return text

    async def respond(
        self: "Zyra",
        msg: Message,
        text: str = "",
        *,
        mode: Optional[str] = "edit",
        redact: bool = True,
        response: Optional[Message] = None,
        **kwargs: Any,
    ) -> Message:
        """
        Always send a chat action before responding/editing.
        Smart-picks action:
          - text only -> typing
          - photo -> upload_photo
          - video -> upload_video
          - document/animation -> upload_document
          - audio -> upload_audio
          - voice -> upload_voice
        """
        # Drop unexpected passthroughs from upper layers
        for k in ("input_arg", "mode"):
            if k in kwargs:
                kwargs.pop(k)

        async def reply(
            reference: Message, *, text: str = "", **kwargs: Any
        ) -> Message:
            # Clean up falsy media kwargs so PTB doesn't choke
            for key in tuple(kwargs.keys()):
                if (
                    key in {"animation", "audio", "document", "photo", "video", "voice"}
                    and not kwargs[key]
                ):
                    del kwargs[key]

            if animation := kwargs.pop("animation", None):
                return await reference.reply_animation(
                    animation=animation, caption=text, **kwargs
                )
            if audio := kwargs.pop("audio", None):
                return await reference.reply_audio(audio=audio, caption=text, **kwargs)
            if document := kwargs.pop("document", None):
                return await reference.reply_document(
                    document=document, caption=text, **kwargs
                )
            if photo := kwargs.pop("photo", None):
                return await reference.reply_photo(photo=photo, caption=text, **kwargs)
            if video := kwargs.pop("video", None):
                return await reference.reply_video(video=video, caption=text, **kwargs)
            if voice := kwargs.pop("voice", None):
                return await reference.reply_voice(voice=voice, caption=text, **kwargs)

            return await reference.reply_text(text, **kwargs)

        if text:
            if redact:
                text = self.redact_message(text)
            text = tg.truncate(text)

        # Clean falsy media kwargs (again in outer scope)
        for key in tuple(kwargs.keys()):
            if (
                key in {"animation", "audio", "document", "photo", "video", "voice"}
                and not kwargs[key]
            ):
                del kwargs[key]

        # Default behavior: if mode == "edit" and we have a response, edit; else reply.
        if mode == "reply" or (response is None and mode == "edit"):
            return await reply(msg, text=text, **kwargs)

        if response is not None and mode == "edit":
            # Can't edit media -> delete old & reply fresh
            if any(
                k in kwargs
                for k in ("animation", "audio", "document", "photo", "video", "voice")
            ):
                try:
                    await response.delete()
                except Exception:
                    pass
                return await reply(
                    msg,
                    text=text or (response.text or response.caption or ""),
                    **kwargs,
                )

            # Avoid passing reply_to on edit
            if "reply_to_message_id" in kwargs:
                del kwargs["reply_to_message_id"]

            return await response.edit_text(text or (response.text or ""), **kwargs)

        raise ValueError(f"Unknown response mode {mode}")
