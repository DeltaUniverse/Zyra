import time
from typing import ClassVar

from telegram import Update
from telegram.ext import ContextTypes

from ..core.module import Module
from ..decorators import handler


class Network(Module):
    name: ClassVar[str] = "Network"

    @handler("ping")
    async def ping(self, update: Update, ctx: ContextTypes) -> None:
        msg = update.effective_message

        start = time.perf_counter()
        sent = await msg.reply_text("Pinging...", do_quote=True)
        end = time.perf_counter()

        ms = (end - start) * 1000
        await sent.edit_text(f"<b>Pong!</b>\n<i>{ms:.2f}</i> ms")
