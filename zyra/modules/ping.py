# zyra/modules/ping.py

import time as _time
from typing import ClassVar

from telegram import Update

from .. import listener, module
from ..util import time


class Ping(module.Module):
    name: ClassVar[str] = "ping"

    @listener.on_commands("ping", "p")
    @listener.desc("Check if the bot is alive and measure latency")
    @listener.usage("ping - Test bot responsiveness")
    async def handle_ping(self, update: Update) -> None:
        msg = update.effective_message
        if not msg:
            return

        start = _time.perf_counter()
        sent = await msg.reply_text("...")
        end = _time.perf_counter()

        latency_us = int((end - start) * 1_000_000)
        latency_str = time.format_duration_us(latency_us)

        await sent.edit_text(f"Pong! <b>{latency_str}</b>")
