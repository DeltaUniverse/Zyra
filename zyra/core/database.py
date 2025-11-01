import asyncpg
from asyncpg import Pool


class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Pool = None

    async def connect(self) -> None:
        if self.pool is not None:
            return

        self.pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=2,
            max_size=10,
            command_timeout=20.0,
            max_inactive_connection_lifetime=300.0,
            max_cached_statement_lifetime=300.0,
            server_settings={"application_name": "Zyra", "jit": "off"},
        )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def __getattr__(self, name: str):
        if self.pool is None:
            raise RuntimeError("Database not connected")

        return getattr(self.pool, name)
