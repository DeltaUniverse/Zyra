from typing import ClassVar, Optional

from telegram import Update
from telegram.ext import ContextTypes

from .. import module
from ..listener import handler, rank_limit


class Operators(module.Module):
    name: ClassVar[str] = "operators"

    @handler(["sudo"], filters=rank_limit("owner"))
    async def sudo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message

        args = context.args or []
        sub = args[0].lower() if args else "list"

        if sub == "list":
            async with self.bot.db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, username FROM users WHERE rank='sudoer' ORDER BY id"
                )
            if not rows:
                await msg.reply_text("⚙️ <b>No sudoers found.</b>")
                return

            lines = []
            for i, r in enumerate(rows, start=1):
                uname = f"@{r['username']}" if r["username"] else "—"
                lines.append(f"<code>{i:02}</code>. {uname} (<code>{r['id']}</code>)")

            await msg.reply_text("🧩 <b>Sudoers List</b>\n" + "\n".join(lines))
            return

        if sub in {"add", "del", "rm", "remove"}:
            target_id: Optional[int] = None

            if msg.reply_to_message and msg.reply_to_message.from_user:
                target_id = msg.reply_to_message.from_user.id
            elif len(args) >= 2 and args[1].lstrip("-").isdigit():
                target_id = int(args[1])

            if not target_id:
                await msg.reply_text("⚠️ <b>Please reply to a user or give an ID!</b>")
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
                    await msg.reply_text(
                        f"✅ <b>Added sudoer</b>\nID: <code>{target_id}</code>"
                    )
                    self.bot.sudoers.add(target_id)
                else:
                    await conn.execute(
                        "UPDATE users SET rank='nobody' WHERE id=$1", target_id
                    )
                    self.bot.sudoers.discard(target_id)
                    await msg.reply_text(
                        f"🗑️ <b>Removed sudoer</b>\nID: <code>{target_id}</code>"
                    )

            return

        await msg.reply_text(
            "ℹ️ <b>Usage:</b>\n"
            "<code>/sudo list</code> — show all sudoers\n"
            "<code>/sudo add &lt;user_id&gt;</code> — add sudoer (or reply)\n"
            "<code>/sudo del &lt;user_id&gt;</code> — remove sudoer (or reply)"
        )
