from typing import ClassVar, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.ext import ContextTypes

from .. import module
from ..listener import handler, rank_limit


class Users(module.Module):
    name: ClassVar[str] = "users"
    _ready: bool = False

    async def on_load(self) -> None:
        async with self.bot.db.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    rank TEXT DEFAULT 'nobody'
                )
                """
            )

    async def _seen(self, u: Optional[User]) -> None:
        if not u or u.id == self.bot.owner_id:
            return

        async with self.bot.db.acquire() as conn:
            row = await conn.fetchrow("SELECT username FROM users WHERE id = $1", u.id)
            if row:
                if row["username"] != u.username:
                    await conn.execute(
                        "UPDATE users SET username = $1 WHERE id = $2", u.username, u.id
                    )
            else:
                await conn.execute(
                    "INSERT INTO users (id, username) VALUES ($1, $2)", u.id, u.username
                )

    @handler("message", priority=110)
    async def on_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._seen(update.effective_user)

    async def _render_userlist(
        self, limit: int, offset: int
    ) -> Tuple[str, InlineKeyboardMarkup]:
        async with self.bot.db.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
            rows = await conn.fetch(
                """
                SELECT id, username, rank
                FROM users
                ORDER BY CASE rank
                           WHEN 'sudoer' THEN 0
                           WHEN 'nobody' THEN 2
                           ELSE 1
                         END,
                         id
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

        groups: Dict[str, List[dict]] = {"sudoer": [], "nobody": []}
        others: Dict[str, List[dict]] = {}

        for r in rows:
            rk = (r["rank"] or "nobody").lower()
            if rk == "sudoer":
                groups["sudoer"].append(r)
            elif rk == "nobody":
                groups["nobody"].append(r)
            else:
                others.setdefault(rk, []).append(r)

        def fmt_user(i: int, r: dict) -> str:
            uname = r["username"]
            mention = (
                f"@{uname}" if uname else f'<a href="tg://user?id={r["id"]}">user</a>'
            )
            return f"{i}. {mention} <code>{r['id']}</code>"

        lines: List[str] = []
        lines.append("<b>👥 User List</b>")
        lines.append(
            f"Total: <b>{total}</b> • Showing: <b>{len(rows)}</b> • Offset: <b>{offset}</b>"
        )
        lines.append("")

        if groups["sudoer"]:
            lines.append("🛡️ <b>Sudoers</b>")
            for idx, r in enumerate(groups["sudoer"], start=1):
                lines.append(fmt_user(idx, r))

            lines.append("")

        if others:
            lines.append("🏷️ <b>Other Ranks</b>")
            for rank_name in sorted(others.keys()):
                lines.append(f"• <b>{rank_name}</b> (<i>{len(others[rank_name])}</i>)")
                for idx, r in enumerate(others[rank_name], start=1):
                    lines.append("   " + fmt_user(idx, r))

                lines.append("")

        if groups["nobody"]:
            lines.append("👤 <b>Nobody</b>")
            for idx, r in enumerate(groups["nobody"], start=1):
                lines.append(fmt_user(idx, r))

            lines.append("")

        if not rows:
            lines.append("<i>No users in this page.</i>")

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔄", callback_data=f"users:refresh:{limit}:{offset}"
                    )
                ],
                [InlineKeyboardButton("✖️", callback_data="users:close")],
            ]
        )
        return "\n".join(lines), kb

    @handler(["users", "userlist"], filters=rank_limit("sudo"))
    async def cmd_userlist(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        args = getattr(context, "args", [])
        try:
            limit = max(1, min(200, int(args[0]))) if len(args) > 0 else 50
            offset = max(0, int(args[1])) if len(args) > 1 else 0
        except ValueError:
            limit, offset = 50, 0

        text, kb = await self._render_userlist(limit, offset)
        await msg.reply_text(text, disable_web_page_preview=True, reply_markup=kb)

    @handler("callback_query", filters=rank_limit("sudo"))
    async def on_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        q = update.callback_query
        data = (q.data or "").split(":")
        if not data or data[0] != "users":
            return

        if len(data) >= 2 and data[1] == "refresh":
            await q.edit_message_text("<i>Refreshing...</i>")
            try:
                limit = int(data[2]) if len(data) > 2 else 50
                offset = int(data[3]) if len(data) > 3 else 0
            except ValueError:
                limit, offset = 50, 0

            text, kb = await self._render_userlist(limit, offset)
            await q.edit_message_text(
                text, disable_web_page_preview=True, reply_markup=kb
            )
            await q.answer("Refreshed")
            return

        if len(data) >= 2 and data[1] == "close":
            await q.message.delete()
            await q.answer("Closed")
