import html
import platform
import sys
from typing import ClassVar

from .. import module
from ..listener import Context, command, desc
from ..util import time


def _f(key: str, val: object) -> str:
    return f'<b>{html.escape(str(key))}:</b> {html.escape("" if val is None else str(val))}'


class System(module.Module):
    name: ClassVar[str] = "system"

    @desc("Measure latency")
    @command("ping", "p")
    async def on_command__ping(self, ctx: Context) -> None:
        t0 = time.usec()
        sent = await ctx.reply("…", parse_mode="HTML")
        dt = time.usec() - t0
        lines = ["<b>Pong</b>", _f("Latency", time.format_duration_us(dt))]
        await sent.edit_text("\n".join(lines), parse_mode="HTML")

    @desc("Bot information")
    @command("bot")
    async def on_command__bot(self, ctx: Context) -> None:
        me = getattr(self.bot, "me", None)
        bot_id = getattr(me, "id", None) or getattr(self.bot, "id", None)
        username = getattr(me, "username", None) or getattr(self.bot, "username", None)
        owner_id = getattr(self.bot, "owner_id", None)
        started_us = getattr(self.bot, "start_time_us", None)
        uptime = (
            time.format_duration_us(time.usec() - started_us) if started_us else "—"
        )
        py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        lines = [
            "<b>Bot Info</b>",
            _f("ID", bot_id or "—"),
            _f("Username", f"@{username}" if username else "—"),
            _f("Owner", owner_id or "—"),
            _f("Uptime", uptime),
            _f("Python", py),
            _f("Platform", f"{platform.system()} {platform.release()}"),
        ]
        await ctx.reply("\n".join(lines), parse_mode="HTML")

    @desc("Chat information")
    @command("chat")
    async def on_command__chat(self, ctx: Context) -> None:
        ch = ctx.chat
        if not ch:
            await ctx.reply(_f("Chat", "—"), parse_mode="HTML")
            return

        title = getattr(ch, "title", None) or getattr(ch, "first_name", None) or "-"
        username = getattr(ch, "username", None)
        lines = [
            "<b>Chat Info</b>",
            _f("ID", ch.id),
            _f("Type", getattr(ch, "type", "—")),
            _f("Title", title),
            _f("User", f"@{username}" if username else "—"),
        ]
        await ctx.reply("\n".join(lines), parse_mode="HTML")

    @desc("Your profile information")
    @command("me")
    async def on_command__me(self, ctx: Context) -> None:
        u = getattr(getattr(ctx, "message", None), "from_user", None)
        if not u:
            await ctx.reply(_f("User", "—"), parse_mode="HTML")
            return

        name = u.full_name if getattr(u, "full_name", None) else (u.first_name or "")
        username = getattr(u, "username", None)
        lang = getattr(u, "language_code", None)
        lines = [
            "<b>User Info</b>",
            _f("ID", u.id),
            _f("Name", name),
            _f("User", f"@{username}" if username else "—"),
            _f("Lang", lang or "—"),
            _f("IsBot", "yes" if getattr(u, "is_bot", False) else "no"),
        ]
        await ctx.reply("\n".join(lines), parse_mode="HTML")

    @desc("Uptime")
    @command("uptime")
    async def on_command__uptime(self, ctx: Context) -> None:
        started_us = getattr(self.bot, "start_time_us", None)
        if not started_us:
            await ctx.reply(_f("Uptime", "—"), parse_mode="HTML")
            return

        dur = time.usec() - started_us
        lines = ["<b>Uptime</b>", _f("Duration", time.format_duration_us(dur))]
        await ctx.reply("\n".join(lines), parse_mode="HTML")
