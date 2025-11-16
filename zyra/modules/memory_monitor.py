import asyncio
import gc
import os

import psutil
from telegram import Update
from telegram.ext import ContextTypes

from ..core.module import Module
from ..decorators import handler, owner_only


class Memory(Module):
    """Monitors and reports memory usage."""

    name = "Memory"

    async def on_load(self) -> None:
        self.process = psutil.Process(os.getpid())

    @handler(["memory", "mem", "ram"])
    async def memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg:
            return

        try:
            mem_info = self.process.memory_info()
            system = psutil.virtual_memory()
        except psutil.Error as e:
            await msg.reply_text(f"❌ psutil error: {e}")
            return

        rss_mb = mem_info.rss / 1024 / 1024
        vms_mb = mem_info.vms / 1024 / 1024

        text = (
            f"<b>Process Memory</b>\n"
            f"• RSS: <code>{rss_mb:,.2f} MB</code>\n"
            f"• VMS: <code>{vms_mb:,.2f} MB</code>\n"
            f"• Usage: <code>{self.process.memory_percent():.1f}%</code>\n\n"
            f"<b>System Memory</b>\n"
            f"• Total: <code>{system.total / 1024 ** 3:,.2f} GB</code>\n"
            f"• Available: <code>{system.available / 1024 ** 3:,.2f} GB</code>\n"
            f"• Used: <code>{system.percent}%</code>"
        )
        await msg.reply_text(text, parse_mode="HTML")

    @handler(["gc"], filters=owner_only)
    async def gc_collect(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        if not msg:
            return

        before = self.process.memory_info().rss / 1024 / 1024
        collected = gc.collect()
        await asyncio.sleep(0.1)
        after = self.process.memory_info().rss / 1024 / 1024
        freed = max(before - after, 0)

        text = (
            f"<b>Garbage Collection</b>\n"
            f"• Objects: <code>{collected}</code>\n"
            f"• Freed: <code>{freed:.2f} MB</code>"
        )
        await msg.reply_text(text, parse_mode="HTML")
