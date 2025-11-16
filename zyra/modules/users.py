import contextlib
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
            if row and row["username"] != user.username:
                await conn.execute(
                    "UPDATE users SET username = $1 WHERE id = $2",
                    user.username,
                    user.id,
                )
            elif not row:
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
                ORDER BY
                    CASE rank
                        WHEN 'sudoer' THEN 0
                        WHEN 'nobody' THEN 2
                        ELSE 1
                    END, id
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

        groups: Dict[str, List[dict]] = {"sudoer": [], "nobody": []}
        others: Dict[str, List[dict]] = {}
        for r in rows:
            rk = (r["rank"] or "nobody").lower()
            if rk in groups:
                groups[rk].append(r)
            else:
                others.setdefault(rk, []).append(r)

        def fmt_user(i: int, r: dict) -> str:
            mention = (
                f"@{r['username']}"
                if r["username"]
                else f'<a href="tg://user?id={r["id"]}">user</a>'
            )
            return f"{i}. {mention} <code>{r['id']}</code>"

        lines: List[str] = [
            "<b>👥 User List</b>",
            f"Total: <b>{total}</b> • Showing: <b>{len(rows)}</b> • Offset: <b>{offset}</b>\n",
        ]
        for section, title in [
            ("sudoer", "🛡️ <b>Sudoers</b>"),
            ("nobody", "👤 <b>Nobody</b>"),
        ]:
            if groups[section]:
                lines.append(title)
                lines.extend(fmt_user(i, r) for i, r in enumerate(groups[section], 1))
                lines.append("")

        if others:
            lines.append("🏷️ <b>Other Ranks</b>")
            for rank, users in sorted(others.items()):
                lines.append(f"• <b>{rank}</b> (<i>{len(users)}</i>)")
                lines.extend(f"   {fmt_user(i, r)}" for i, r in enumerate(users, 1))
                lines.append("")

        if not rows:
            lines.append("<i>No users in this page.</i>")

        has_prev = offset > 0
        has_next = offset + limit < total
        nav_buttons = []
        if has_prev:
            nav_buttons.append(
                InlineKeyboardButton(
                    "⬅️ Prev",
                    callback_data=f"users:refresh:{limit}:{max(0, offset - limit)}",
                )
            )

        if has_next:
            nav_buttons.append(
                InlineKeyboardButton(
                    "➡️ Next", callback_data=f"users:refresh:{limit}:{offset + limit}"
                )
            )

        kb_rows = []
        if nav_buttons:
            kb_rows.append(nav_buttons)

        kb_rows.append([InlineKeyboardButton("✖️ Close", callback_data="users:close")])
        kb = InlineKeyboardMarkup(kb_rows)
        return "\n".join(lines), kb

    @handler(["users", "userlist"], filters=sudo_only)
    async def cmd_userlist(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        args = context.args or []
        try:
            limit = max(1, min(200, int(args[0]))) if args else 10
            offset = max(0, int(args[1])) if len(args) > 1 else 0
        except ValueError:
            limit, offset = 10, 0

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

        action = parts[0]
        if action == "refresh":
            with contextlib.suppress(Exception):
                await q.edit_message_text("<i>…</i>")

            try:
                limit = int(parts[1]) if len(parts) > 1 else 10
                offset = int(parts[2]) if len(parts) > 2 else 0
                text, kb = await self._render_userlist(limit, offset)
                await q.edit_message_text(
                    text, disable_web_page_preview=True, reply_markup=kb
                )
                await q.answer("Updated")
            except Exception as e:
                await q.answer(f"Error: {e}")
        elif action == "close":
            with contextlib.suppress(Exception):
                await q.message.delete()

            await q.answer("Closed")
