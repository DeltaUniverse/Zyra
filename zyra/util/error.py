import asyncio
import html
import time
import traceback
from typing import Callable, Optional

from telegram.error import (
    BadRequest,
    Conflict,
    Forbidden,
    InvalidToken,
    NetworkError,
    RetryAfter,
    TelegramError,
    TimedOut,
)
from telegram.ext import ContextTypes


def format_exception_html(exc: BaseException, *, limit: Optional[int] = 8) -> str:
    tb = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__, limit=limit)
    )
    return f"<pre>{html.escape(tb)}</pre>"


def make_error_handler(
    owner_id: int,
    *,
    logger=None,
    redact: Optional[Callable[[str], str]] = None,
    notify_cooldown_s: int = 20,
):
    last_notify_ts = 0.0
    redact = redact or (lambda s: s)

    async def _notify_owner(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        nonlocal last_notify_ts
        now = time.monotonic()
        if now - last_notify_ts < notify_cooldown_s:
            return

        last_notify_ts = now
        try:
            await context.bot.send_message(
                owner_id, text, disable_web_page_preview=True
            )
        except Exception as e:
            if logger:
                logger.debug("Failed to notify owner: %s", e)

    async def _handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        exc = context.error
        log = logger or getattr(getattr(context, "application", None), "logger", None)
        if log:
            log.error("Exception in handler", exc_info=exc)

        if isinstance(exc, RetryAfter):
            wait = max(1, int(getattr(exc, "retry_after", 1)))
            if log:
                log.warning("Flood control: retry after %ss", wait)

            await asyncio.sleep(wait)
            return

        if isinstance(exc, TimedOut):
            if log:
                log.warning("Timed out (transient).")

            return

        if isinstance(exc, NetworkError):
            if log:
                log.warning("Network issue (transient): %s", exc)

            return

        if isinstance(exc, BadRequest):
            text = str(exc).lower()
            benign = (
                "message to delete not found" in text
                or "message to edit not found" in text
                or "message is not modified" in text
                or ("query is too old" in text)
                or ("can't parse entities" in text)
            )
            if benign:
                if log:
                    log.info("Benign BadRequest: %s", exc)

                return

            html_tb = redact(format_exception_html(exc))
            await _notify_owner(
                context, f"⚠️ <b>BadRequest</b>\n{html.escape(str(exc))}\n\n{html_tb}"
            )
            return

        if isinstance(exc, Forbidden):
            if log:
                log.info("Forbidden (insufficient rights / user blocked bot): %s", exc)

            return

        if isinstance(exc, Conflict):
            await _notify_owner(
                context,
                f"⚠️ <b>Conflict</b> — multiple runners? Ensure only one poller/webhook is active.\n{html.escape(str(exc))}",
            )
            return

        if isinstance(exc, InvalidToken):
            await _notify_owner(
                context, "❌ <b>Invalid bot token</b>. Check TELEGRAM_TOKEN."
            )
            return

        if isinstance(exc, TelegramError):
            html_tb = redact(format_exception_html(exc))
            await _notify_owner(context, f"⚠️ <b>TelegramError</b>\n{html_tb}")
            return

        html_tb = redact(format_exception_html(exc))
        await _notify_owner(context, f"⚠️ <b>Exception</b>\n{html_tb}")

    return _handler
