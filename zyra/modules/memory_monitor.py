import asyncio
import gc
import os

import psutil
from telegram import Update
from telegram.ext import ContextTypes

from ..core.module_manager import ModuleBase
from ..decorators import handler, requires_owner


class MemoryMonitor(ModuleBase):
    name = "Memory"

    async def on_load(self) -> None:
        self.process = psutil.Process(os.getpid())

    @handler(["memory", "mem", "ram"])
    async def memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg:
            return

        mem_info = self.process.memory_info()
        mem_percent = self.process.memory_percent()

        rss_mb = mem_info.rss / 1024 / 1024
        vms_mb = mem_info.vms / 1024 / 1024

        system_mem = psutil.virtual_memory()
        total_gb = system_mem.total / 1024 / 1024 / 1024
        available_gb = system_mem.available / 1024 / 1024 / 1024
        used_percent = system_mem.percent

        text = (
            f"<b>Process Memory:</b>\n"
            f"├ RSS: <code>{rss_mb:.2f} MB</code>\n"
            f"├ VMS: <code>{vms_mb:.2f} MB</code>\n"
            f"└ Usage: <code>{mem_percent:.1f}%</code>\n\n"
            f"<b>System Memory:</b>\n"
            f"├ Total: <code>{total_gb:.2f} GB</code>\n"
            f"├ Available: <code>{available_gb:.2f} GB</code>\n"
            f"└ Used: <code>{used_percent}%</code>"
        )

        await msg.reply_text(text, parse_mode="HTML")

    @handler(["gc"], filters=requires_owner)
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
        freed = before - after

        text = (
            f"<b>Garbage Collection:</b>\n"
            f"├ Objects: <code>{collected}</code>\n"
            f"├ Before: <code>{before:.2f} MB</code>\n"
            f"├ After: <code>{after:.2f} MB</code>\n"
            f"└ Freed: <code>{freed:.2f} MB</code>"
        )

        await msg.reply_text(text, parse_mode="HTML")
