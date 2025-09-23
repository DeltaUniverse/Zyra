import time as _time
from typing import ClassVar

from .. import listener, module
from ..util import time


class Ping(module.Module):
    name: ClassVar[str] = "ping"

    @listener.on_commands("ping", "p")
    @listener.desc("Check if the bot is alive and measure latency")
    @listener.usage("ping - Test bot responsiveness")
    async def handle_ping(self, ctx: listener.Context) -> None:
        start = _time.perf_counter()
        sent = await ctx.respond("🏓 Pinging...")
        end = _time.perf_counter()
        latency_us = int((end - start) * 1000000)
        latency_str = time.format_duration_us(latency_us)
        response_lines = [
            "🏓 <b>Pong!</b>",
            f"⚡ Latency: <code>{latency_str}</code>",
            f"👤 User: <code>{(ctx.msg.from_user.first_name if ctx.msg.from_user else 'Unknown')}</code>",
            f"💬 Chat: <code>{ctx.chat.title or ctx.chat.first_name or 'Private'}</code>",
            f"📝 Command: <code>{ctx.invoker}</code>",
        ]
        await sent.edit_text("\n".join(response_lines))
