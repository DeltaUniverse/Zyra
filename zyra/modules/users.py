# users.py  (PTB version)
from typing import ClassVar, Optional

from telegram import Update, User
from telegram.ext import ContextTypes

from .. import module
from ..listener import handler


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
            await conn.execute(
                """
                INSERT INTO users (id, username)
                VALUES ($1, $2)
                ON CONFLICT (id) DO UPDATE
                SET username = COALESCE(EXCLUDED.username, users.username)
                """,
                u.id,
                u.username,
            )

    @handler("message")
    async def on_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._seen(update.effective_user)
