from typing import Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.ext import ContextTypes

from ..core.module import Module
from ..decorators import handler, parse_callback, sudo_only


class Users(Module):
    name = "users"

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

    async def _update_user(self, user: Optional[User]) -> None:
        if not user or user.id == self.bot.owner_id:
            return

        async with self.bot.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT username FROM users WHERE id = $1", user.id
            )
            if row:
                if row["username"] != user.username:
                    await conn.execute(
                        "UPDATE users SET username = $1 WHERE id = $2",
                        user.username,
                        user.id,
                    )
            else:
                await conn.execute(
                    "INSERT INTO users (id, username) VALUES ($1, $2)",
                    user.id,
                    user.username,
                )

    @handler("message", priority=110)
    async def on_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._update_user(update.effective_user)

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

        lines: List[str] = [
            "<b>👥 User List</b>",
            f"Total: <b>{total}</b> • Showing: <b>{len(rows)}</b> • Offset: <b>{offset}</b>",
            "",
        ]

        if groups["sudoer"]:
            lines.append("🛡️ <b>Sudoers</b>")
            lines.extend(fmt_user(i, r) for i, r in enumerate(groups["sudoer"], 1))
            lines.append("")

        if others:
            lines.append("🏷️ <b>Other Ranks</b>")
            for rank_name in sorted(others.keys()):
                lines.append(f"• <b>{rank_name}</b> (<i>{len(others[rank_name])}</i>)")
                lines.extend(
                    f"   {fmt_user(i, r)}" for i, r in enumerate(others[rank_name], 1)
                )
                lines.append("")

        if groups["nobody"]:
            lines.append("👤 <b>Nobody</b>")
            lines.extend(fmt_user(i, r) for i, r in enumerate(groups["nobody"], 1))
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

    @handler(["users", "userlist"], filters=sudo_only)
    async def cmd_userlist(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        args = context.args or []

        try:
            limit = max(1, min(200, int(args[0]))) if args else 50
            offset = max(0, int(args[1])) if len(args) > 1 else 0
        except ValueError:
            limit, offset = 50, 0

        text, kb = await self._render_userlist(limit, offset)
        await msg.reply_text(text, disable_web_page_preview=True, reply_markup=kb)

    @handler("callback_query", filters=sudo_only)
    async def on_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        q = update.callback_query
        parts = parse_callback(q.data or "", "users")
        if not parts:
            return

        action = parts[0] if parts else None

        if action == "refresh":
            await q.edit_message_text("<i>Refreshing...</i>")
            try:
                limit = int(parts[1]) if len(parts) > 1 else 50
                offset = int(parts[2]) if len(parts) > 2 else 0
            except (ValueError, IndexError):
                limit, offset = 50, 0

            text, kb = await self._render_userlist(limit, offset)
            await q.edit_message_text(
                text, disable_web_page_preview=True, reply_markup=kb
            )
            await q.answer("Refreshed")

        elif action == "close":
            await q.message.delete()
            await q.answer("Closed")
