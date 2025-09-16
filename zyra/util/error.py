"""Exception formatting & PTB error handler utilities (Google-style docstrings).

This module centralizes:
  1) Plain-text traceback formatting (`format_exception`).
  2) HTML-safe traceback formatting for Telegram (`format_exception_html`).
  3) A factory that creates a PTB-compatible error handler
     (`make_error_handler`) which logs and notifies the owner.
"""

import html
import os
import traceback
from typing import List, Optional, Protocol


class RedactFn(Protocol):
    def __call__(self, text: str) -> str: ...


def _relativize_filenames(
    frames: List[traceback.FrameSummary], *, base: Optional[str] = None
) -> None:
    """Relativize filenames in traceback frames in-place.

    Args:
        frames: List of traceback frames to update.
        base: Base directory to relativize against. Defaults to the
            current working directory.
    """
    cwd = base or os.getcwd()
    for f in frames:
        if cwd and f.filename.startswith(cwd):
            f.filename = os.path.relpath(f.filename, start=cwd)


def format_exception(
    exp: BaseException,
    *,
    tb: Optional[List[traceback.FrameSummary]] = None,
    limit: Optional[int] = None,
    make_relative: bool = True,
    relative_to: Optional[str] = None,
) -> str:
    """Format an exception traceback as plain text.

    Args:
        exp: The exception instance to format.
        tb: Optional pre-extracted traceback frames. If None, uses
            ``exp.__traceback__``.
        limit: Maximum number of frames to include. Defaults to None
            (include all).
        make_relative: Whether to convert absolute filenames under the
            working directory to relative paths.
        relative_to: Custom base directory for relativizing. Defaults to
            current working directory.

    Returns:
        A string with the formatted traceback and error message.
    """
    if tb is None:
        if exp.__traceback__ is not None:
            tb = traceback.extract_tb(exp.__traceback__, limit=limit)
        else:
            tb = []

    if make_relative:
        _relativize_filenames(tb, base=relative_to)

    stack = "".join(traceback.format_list(tb))
    msg = str(exp)
    suffix = f": {msg}" if msg else ""
    return f"Traceback (most recent call last):\n{stack}{type(exp).__name__}{suffix}"


def format_exception_html(
    exp: BaseException,
    *,
    tb: Optional[List[traceback.FrameSummary]] = None,
    limit: Optional[int] = None,
    make_relative: bool = True,
    relative_to: Optional[str] = None,
) -> str:
    """Format an exception traceback as HTML for Telegram.

    Escapes the traceback text and wraps it in <pre>…</pre>.

    Args:
        exp: The exception instance to format.
        tb: Optional pre-extracted traceback frames. If None, uses
            ``exp.__traceback__``.
        limit: Maximum number of frames to include.
        make_relative: Whether to relativize file paths.
        relative_to: Base directory for relativizing paths.

    Returns:
        A safe HTML string suitable for sending with ``ParseMode.HTML``.
    """
    plain = format_exception(
        exp, tb=tb, limit=limit, make_relative=make_relative, relative_to=relative_to
    )
    return f"<pre>{html.escape(plain)}</pre>"


def make_error_handler(
    owner_id: int, *, logger=None, redact: Optional[RedactFn] = None
):
    """Create a PTB error handler coroutine that logs and notifies the owner.

    The returned coroutine matches PTB's error handler signature:
    ``async def handler(update, context) -> None``.

    Behavior:
      * Logs the exception (uses provided `logger` if given, otherwise
        `context.application.logger`).
      * Builds an HTML-safe traceback with :func:`format_exception_html`.
      * Optionally redacts sensitive data via `redact(text)`.
      * Sends the error report to `owner_id`.

    Args:
        owner_id: Telegram user ID to notify.
        logger: Optional logger to use for logging exceptions.
        redact: Optional function to sanitize the outgoing message.

    Returns:
        An async function usable with ``Application.add_error_handler(...)``.
    """

    async def _handler(update, context) -> None:  # PTB signature
        log = logger or getattr(context.application, "logger", None)
        if log:
            log.error("Exception in handler", exc_info=context.error)

        try:
            html_text = format_exception_html(context.error)
            if redact:
                html_text = redact(html_text)

            msg = f"⚠️ <b>Exception</b>:\n{html_text}"
            await context.bot.send_message(
                chat_id=owner_id, text=msg, parse_mode="HTML"
            )
        except Exception as send_err:
            if log:
                log.error("Failed to notify owner", exc_info=send_err)

    return _handler
