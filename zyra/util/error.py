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
    """Return an HTML-safe traceback for an exception.

    Args:
        exc: The exception to format.
        limit: Maximum traceback frames to include. If None, include all.

    Returns:
        A string containing a <pre>...</pre>-wrapped HTML-escaped traceback.
    """
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
    """Create a PTB-compatible global error handler.

    This handler classifies common PTB errors, logs appropriately, and
    rate-limits owner notifications to avoid spam.

    Args:
        owner_id: Telegram user ID to notify for important errors.
        logger: Optional logger. If not provided, falls back to application's logger.
        redact: Optional callable to sanitize sensitive strings before sending/logging.
        notify_cooldown_s: Minimum seconds between owner notifications.

    Returns:
        An async function suitable for Application.add_error_handler().
    """
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
        """PTB error handler.

        Args:
            update: The update that caused the error (may be None).
            context: PTB context; context.error holds the exception.
        """
        exc = context.error  # type: ignore[attr-defined]
        log = logger or getattr(getattr(context, "application", None), "logger", None)

        if log:
            log.error("Exception in handler", exc_info=exc)

        # Transient / flow-control errors
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

        # BadRequest classification
        if isinstance(exc, BadRequest):
            text = str(exc).lower()
            benign = (
                "message to delete not found" in text
                or "message to edit not found" in text
                or "message is not modified" in text
                or "query is too old" in text
                or "can't parse entities" in text
            )
            if benign:
                if log:
                    log.info("Benign BadRequest: %s", exc)

                return

            html_tb = redact(format_exception_html(exc))
            await _notify_owner(
                context,
                "⚠️ <b>BadRequest</b>\n" f"{html.escape(str(exc))}\n\n" f"{html_tb}",
            )
            return

        # Permissions/runner issues
        if isinstance(exc, Forbidden):
            if log:
                log.info("Forbidden (insufficient rights / user blocked bot): %s", exc)

            return

        if isinstance(exc, Conflict):
            await _notify_owner(
                context,
                "⚠️ <b>Conflict</b> — multiple runners? Ensure only one poller/webhook is active.\n"
                f"{html.escape(str(exc))}",
            )
            return

        if isinstance(exc, InvalidToken):
            await _notify_owner(
                context, "❌ <b>Invalid bot token</b>. Check TELEGRAM_TOKEN."
            )
            return

        # Other TelegramError
        if isinstance(exc, TelegramError):
            html_tb = redact(format_exception_html(exc))
            await _notify_owner(context, f"⚠️ <b>TelegramError</b>\n{html_tb}")
            return

        # Unknown exception
        html_tb = redact(format_exception_html(exc))
        await _notify_owner(context, f"⚠️ <b>Exception</b>\n{html_tb}")

    return _handler
