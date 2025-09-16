"""A simple module to check bot latency and responsiveness.

This module provides a 'ping' command that allows users to verify that the
bot is online and responsive. It works by sending a message and measuring the
time it takes for the Telegram API call to complete. The initial message is
then edited to show the calculated round-trip latency.
"""

import time as _time
from typing import ClassVar

from .. import listener, module
from ..util import time


class Ping(module.Module):
    """Implements the 'ping' command to measure bot latency."""

    name: ClassVar[str] = "ping"

    @listener.on_commands("ping", "p")
    @listener.desc("Check if the bot is alive and measure latency")
    @listener.usage("ping - Test bot responsiveness")
    async def handle_ping(self, ctx: listener.Context) -> None:
        """Measures and reports the bot's command processing latency.

        This function records the time before and after sending an initial message.
        It then calculates the duration and edits the message to display the
        round-trip time along with contextual information like the user and chat.

        Args:
            ctx: The command context provided by the listener.
        """
        start = _time.perf_counter()
        sent = await ctx.respond("🏓 Pinging...")
        end = _time.perf_counter()

        latency_us = int((end - start) * 1_000_000)
        latency_str = time.format_duration_us(latency_us)

        # Show some additional info using the Context object
        response_lines = [
            "🏓 <b>Pong!</b>",
            f"⚡ Latency: <code>{latency_str}</code>",
            f"👤 User: <code>{ctx.msg.from_user.first_name if ctx.msg.from_user else 'Unknown'}</code>",
            f"💬 Chat: <code>{ctx.chat.title or ctx.chat.first_name or 'Private'}</code>",
            f"📝 Command: <code>{ctx.invoker}</code>",
        ]

        await sent.edit_text("\n".join(response_lines))
