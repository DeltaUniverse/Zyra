import time as _time
from typing import ClassVar

from .. import module
from ..listener import Context
from ..util import time


class Ping(module.Module):
    name: ClassVar[str] = "ping"

    async def on_command(self, ctx: Context) -> None:
        # Terima hanya 'ping' atau 'p'
        if ctx.invoker not in {"ping", "p"}:
            return

        start = _time.perf_counter()
        sent = await ctx.respond("🏓 Pinging...")
        end = _time.perf_counter()

        latency_us = int((end - start) * 1_000_000)
        latency_str = time.format_duration_us(latency_us)

        user_name = ctx.msg.from_user.first_name if ctx.msg.from_user else "Unknown"
        chat_label = (
            ctx.chat.title or getattr(ctx.chat, "first_name", None) or "Private"
        )

        response_lines = [
            "🏓 <b>Pong!</b>",
            f"⚡ Latency: <code>{latency_str}</code>",
            f"👤 User: <code>{user_name}</code>",
            f"💬 Chat: <code>{chat_label}</code>",
            f"📝 Command: <code>{ctx.invoker}</code>",
        ]
        await sent.edit_text("\n".join(response_lines))
