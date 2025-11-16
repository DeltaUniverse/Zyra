from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..core.module import Module
from ..decorators import handler, owner_only, sudo_only


class Operators(Module):
    name = "operators"

    @staticmethod
    def _resolve_target_id(msg, args) -> Optional[int]:
        if msg.reply_to_message and msg.reply_to_message.from_user:
            return msg.reply_to_message.from_user.id

        if len(args) >= 2 and args[1].lstrip("-").isdigit():
            return int(args[1])

        return None

    async def _send_rank_list(
        self, msg, rank: str, title: str, empty_text: str
    ) -> None:
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

    @handler(["sudo"], filters=owner_only)
    async def sudo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        args = context.args or []
        sub = args[0].lower() if args else "list"

        if sub == "list":
            await self._send_rank_list(
                msg,
                rank="sudoer",
                title="🧩 <b>Sudoers List</b>",
                empty_text="⚙️ <b>No sudoers found.</b>",
            )
            return

        if sub in {"add", "del", "rm", "remove"}:
            target_id = self._resolve_target_id(msg, args)

            if not target_id:
                await msg.reply_text(
                    "⚠️ <b>Please reply to a user or provide an ID.</b>"
                )
                return

            async with self.bot.db.acquire() as conn:
                if sub == "add":
                    await conn.execute(
                        """
                        INSERT INTO users (id, rank)
                        VALUES ($1, 'sudoer')
                        ON CONFLICT (id) DO UPDATE SET rank='sudoer'
                        """,
                        target_id,
                    )
                    self.bot.sudoers.add(target_id)
                    await msg.reply_text(
                        f"✅ <b>Added sudoer:</b> <code>{target_id}</code>"
                    )
                else:
                    await conn.execute(
                        "UPDATE users SET rank='nobody' WHERE id=$1", target_id
                    )
                    self.bot.sudoers.discard(target_id)
                    await msg.reply_text(
                        f"🗑️ <b>Removed sudoer:</b> <code>{target_id}</code>"
                    )

            return

        await msg.reply_text(
            "ℹ️ <b>Usage:</b>\n"
            "<code>/sudo list</code> — show all sudoers\n"
            "<code>/sudo add 12345</code> — add sudoer (or reply)\n"
            "<code>/sudo del 12345</code> — remove sudoer (or reply)"
        )

    @handler(["staff"], filters=sudo_only)
    async def staff(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        args = context.args or []
        sub = args[0].lower() if args else "list"

        if sub == "list":
            await self._send_rank_list(
                msg,
                rank="staff",
                title="👥 <b>Staff List</b>",
                empty_text="💼 <b>No staff found.</b>",
            )
            return

        if sub in {"add", "del", "rm", "remove"}:
            target_id = self._resolve_target_id(msg, args)

            if not target_id:
                await msg.reply_text(
                    "⚠️ <b>Please reply to a user or provide an ID.</b>"
                )
                return

            async with self.bot.db.acquire() as conn:
                if sub == "add":
                    await conn.execute(
                        """
                        INSERT INTO users (id, rank)
                        VALUES ($1, 'staff')
                        ON CONFLICT (id) DO UPDATE SET rank='staff'
                        """,
                        target_id,
                    )
                    await msg.reply_text(
                        f"✅ <b>Added staff:</b> <code>{target_id}</code>"
                    )
                else:
                    await conn.execute(
                        "UPDATE users SET rank='nobody' WHERE id=$1", target_id
                    )
                    await msg.reply_text(
                        f"🗑️ <b>Removed staff:</b> <code>{target_id}</code>"
                    )

            return

        await msg.reply_text(
            "ℹ️ <b>Usage:</b>\n"
            "<code>/staff list</code> — show all staff\n"
            "<code>/staff add 12345</code> — add staff (or reply)\n"
            "<code>/staff del 12345</code> — remove staff (or reply)"
        )
