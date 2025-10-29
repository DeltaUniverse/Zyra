from typing import TYPE_CHECKING, Any

import asyncpg
from asyncpg import Pool

from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


class DatabaseProvider(ZyraBase):
    db: Pool

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        section = self.config.get("bot") or {}
        dsn = section.get("db_uri")
        if not dsn:
            raise SystemExit("Missing database.db_uri in config")

        self._db_dsn = dsn
        self.db = None
        super().__init__(**kwargs)

    async def setup_database(self: "Zyra") -> None:
        if self.db is None:
            self.db = await asyncpg.create_pool(
                dsn=self._db_dsn,
                min_size=2,
                max_size=10,
                command_timeout=30.0,
                max_inactive_connection_lifetime=300.0,
                server_settings={"application_name": "Zyra", "jit": "off"},
            )
            self.log.info("Database pool initialized")

    async def close_database(self: "Zyra") -> None:
        if self.db is not None:
            await self.db.close()
            self.log.info("Database pool closed")
