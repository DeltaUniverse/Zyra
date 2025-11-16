from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..core.module import Module
from ..decorators import handler, owner_only, sudo_only


class Operators(Module):
    """Manage sudo and staff ranks."""

    name = "operators"

    @staticmethod
    def _resolve_target_id(msg, args) -> Optional[int]:
        """Resolve user ID from reply or argument."""
        if msg.reply_to_message and msg.reply_to_message.from_user:
            return msg.reply_to_message.from_user.id

        if len(args) >= 2 and args[1].lstrip("-").isdigit():
            return int(args[1])

        return None

    async def _send_rank_list(
        self, msg, rank: str, title: str, empty_text: str
    ) -> None:
        """Send formatted rank list."""
        async with self.bot.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, username FROM users WHERE rank=$1 ORDER BY id", rank
            )

        if not rows:
            await msg.reply_text(empty_text)
            return

        lines = [
            (
                f"<code>{i:02}</code>. @{r['username']}"
                if r["username"]
                else f"<code>{i:02}</code>. — (<code>{r['id']}</code>)"
            )
            for i, r in enumerate(rows, start=1)
        ]
        await msg.reply_text(f"{title}\n" + "\n".join(lines))

    async def _update_rank(self, msg, user_id: int, rank: str, add: bool) -> None:
        """Insert or update user rank."""
        async with self.bot.db.acquire() as conn:
            if add:
                await conn.execute(
                    """
                    INSERT INTO users (id, rank)
                    VALUES ($1, $2)
                    ON CONFLICT (id) DO UPDATE SET rank=$2
                    """,
                    user_id,
                    rank,
                )
            else:
                await conn.execute(
                    "UPDATE users SET rank='nobody' WHERE id=$1", user_id
                )

        self.bot.sudoers.discard(user_id)
        if add and rank == "sudoer":
            self.bot.sudoers.add(user_id)

        status = "✅ Added" if add else "🗑️ Removed"
        await msg.reply_text(f"{status} <b>{rank}</b>: <code>{user_id}</code>")

    @handler(["sudo"], filters=owner_only)
    async def sudo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Command handler for sudoers."""
        msg, args = update.effective_message, (context.args or [])
        sub = args[0].lower() if args else "list"

        if sub == "list":
            await self._send_rank_list(
                msg, "sudoer", "🧩 <b>Sudoers</b>", "⚙️ None found."
            )
            return

        if sub in {"add", "del", "rm", "remove"}:
            user_id = self._resolve_target_id(msg, args)
            if not user_id:
                await msg.reply_text("⚠️ Reply to a user or provide an ID.")
                return

            await self._update_rank(msg, user_id, "sudoer", add=(sub == "add"))
            return

        await msg.reply_text(
            "ℹ️ <b>Usage:</b>\n"
            "<code>/sudo list</code>\n"
            "<code>/sudo add &lt;id&gt;</code>\n"
            "<code>/sudo del &lt;id&gt;</code>"
        )

    @handler(["staff"], filters=sudo_only)
    async def staff(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Command handler for staff."""
        msg, args = update.effective_message, (context.args or [])
        sub = args[0].lower() if args else "list"

        if sub == "list":
            await self._send_rank_list(
                msg, "staff", "👥 <b>Staff</b>", "💼 None found."
            )
            return

        if sub in {"add", "del", "rm", "remove"}:
            user_id = self._resolve_target_id(msg, args)
            if not user_id:
                await msg.reply_text("⚠️ Reply to a user or provide an ID.")
                return

            await self._update_rank(msg, user_id, "staff", add=(sub == "add"))
            return

        await msg.reply_text(
            "ℹ️ <b>Usage:</b>\n"
            "<code>/staff list</code>\n"
            "<code>/staff add &lt;id&gt;</code>\n"
            "<code>/staff del &lt;id&gt;</code>"
        )
