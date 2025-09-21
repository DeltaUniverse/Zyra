from typing import ClassVar, Optional

from telegram import Chat, Update, User
from telegram.ext import CallbackContext

from .. import module


class Stats(module.Module):
    name: ClassVar[str] = "Stats"

    async def on_load(self) -> None:
        await self._migrate()

        self.bot.register_listener(
            mod=self, event_name="stat_event", function=self.on_stat_event, priority=0
        )
        self.bot.register_listener(
            mod=self,
            event_name="message",
            function=self.show_stats,
            priority=100,
            commands=("stats",),
            filters_object=None,
            description="Show stats summary (owner only)",
            usage="stats",
        )

    async def _migrate(self) -> None:
        q1 = """
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id BIGINT PRIMARY KEY,
            messages BIGINT DEFAULT 0,
            commands BIGINT DEFAULT 0,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        q2 = """
        CREATE TABLE IF NOT EXISTS chat_stats (
            chat_id BIGINT PRIMARY KEY,
            messages BIGINT DEFAULT 0,
            commands BIGINT DEFAULT 0,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        q3 = """
        CREATE TABLE IF NOT EXISTS command_counters (
            command TEXT PRIMARY KEY,
            n BIGINT DEFAULT 0,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            await self.bot.db.execute(q1)
            await self.bot.db.execute(q2)
            await self.bot.db.execute(q3)
        except Exception as e:
            self.log.error(f"Stats migration failed: {e}")

    async def _bump_user(self, user: Optional[User], *, is_command: bool) -> None:
        if not user:
            return

        try:
            field = "commands" if is_command else "messages"
            q = f"""
            INSERT INTO user_stats (user_id, {field}, last_seen)
            VALUES ($1, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE
              SET {field} = user_stats.{field} + 1,
                  last_seen = CURRENT_TIMESTAMP;
            """
            await self.bot.db.execute(q, user.id)
        except Exception as e:
            self.log.error(f"user_stats bump failed for {user.id}: {e}")

    async def _bump_chat(self, chat: Optional[Chat], *, is_command: bool) -> None:
        if not chat:
            return

        try:
            field = "commands" if is_command else "messages"
            q = f"""
            INSERT INTO chat_stats (chat_id, {field}, last_activity)
            VALUES ($1, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (chat_id) DO UPDATE
              SET {field} = chat_stats.{field} + 1,
                  last_activity = CURRENT_TIMESTAMP;
            """
            await self.bot.db.execute(q, chat.id)
        except Exception as e:
            self.log.error(f"chat_stats bump failed for {chat.id}: {e}")

    async def _bump_command(self, cmd: str) -> None:
        if not cmd:
            return

        try:
            q = """
            INSERT INTO command_counters (command, n, last_used)
            VALUES ($1, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (command) DO UPDATE
              SET n = command_counters.n + 1,
                  last_used = CURRENT_TIMESTAMP;
            """
            await self.bot.db.execute(q, cmd)
        except Exception as e:
            self.log.error(f"command bump failed for /{cmd}: {e}")

    async def on_stat_event(
        self,
        stat_key: str,
        update: Optional[Update] = None,
        raw_context: Optional[CallbackContext] = None,
    ) -> None:
        try:
            user = update.effective_user if update else None
            chat = update.effective_chat if update else None

            if stat_key == "msg":
                await self._bump_user(user, is_command=False)
                await self._bump_chat(chat, is_command=False)
                return

            if stat_key.startswith("cmd:"):
                cmd = stat_key[4:]
                if cmd:
                    await self._bump_command(cmd)
                    await self._bump_user(user, is_command=True)
                    await self._bump_chat(chat, is_command=True)

                return
        except Exception as exc:
            tb = exc.__traceback__
            while tb and tb.tb_next:
                tb = tb.tb_next

            f = tb.tb_frame.f_code.co_filename if tb else "?"
            ln = tb.tb_lineno if tb else "?"
            self.log.error(f"{exc.__class__.__name__}: {exc} at {f}:{ln}")

    async def show_stats(self, ctx) -> None:
        u = ctx.msg.from_user
        if not u or u.id != self.bot.owner_id:
            return

        try:
            total_users = await self.bot.db.fetchval("SELECT COUNT(*) FROM user_stats")
            total_chats = await self.bot.db.fetchval("SELECT COUNT(*) FROM chat_stats")
            total_msgs = await self.bot.db.fetchval(
                "SELECT COALESCE(SUM(messages),0) FROM user_stats"
            )
            total_cmds = await self.bot.db.fetchval(
                "SELECT COALESCE(SUM(commands),0) FROM user_stats"
            )
            top_cmds = await self.bot.db.fetch(
                "SELECT command, n FROM command_counters ORDER BY n DESC, command ASC LIMIT 10"
            )

            lines = [
                "📊 <b>Stats</b>",
                f"👥 Users: <b>{total_users}</b>",
                f"👥 Chats: <b>{total_chats}</b>",
                f"💬 Messages: <b>{total_msgs}</b>",
                f"⌨️ Commands: <b>{total_cmds}</b>",
                "",
                "🏆 <b>Top Commands</b>",
            ]
            if top_cmds:
                for i, r in enumerate(top_cmds, 1):
                    lines.append(f"{i}. /{r['command']}: <b>{r['n']}</b>")
            else:
                lines.append("No commands yet.")

            await ctx.respond("\n".join(lines), parse_mode="HTML")
        except Exception as e:
            await ctx.respond(f"❌ Database error: {e}")
            self.log.error(f"stats summary failed: {e}")
