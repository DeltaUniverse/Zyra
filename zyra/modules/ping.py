import time
from typing import ClassVar

from .. import command, module


class Ping(module.Module):
    name: ClassVar = "ping"

    @command.desc("Check if the bot is alive and measure latency")
    async def cmd_sping(self, ctx: command.Context):
        start = time.perf_counter()
        await ctx.respond("🏓 <b>Pong...</b>")
        end = time.perf_counter()

        latency_ms = (end - start) * 1000
        await ctx.respond(f"🏓 Pong! <code>{latency_ms:.0f} ms</code>")
