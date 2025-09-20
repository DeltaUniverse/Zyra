"""Database provider for Zyra with asyncpg (pool config hardcoded).

- Hardcoded pool tuning (min/max, timeouts) for now, DSN still from config.
- Safe acquire with timeout and proper transaction context manager.
- Convenience methods: execute, fetch, fetchrow, fetchval, executemany, copy.
- Health-check helper.
- Clean lifecycle hooks (init/close).

Expected minimal config:

[database]
# Required only: DSN
# e.g. postgresql://user:pass@host:5432/db
 db_uri = "postgresql://..."
"""

from __future__ import annotations

import asyncio
import contextlib
import time as _time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Iterable, List, Optional, Sequence, Union

try:
    import asyncpg
    from asyncpg import Connection, Pool, Record
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]
    Pool = Record = Connection = None  # type: ignore[misc]

from .base import ZyraBase

if TYPE_CHECKING:  # pragma: no cover
    from .bot import Zyra

_MIN_SIZE = 2
_MAX_SIZE = 10
_ACQUIRE_TIMEOUT_S = 5.0
_COMMAND_TIMEOUT_S = 30.0
_MAX_INACTIVE_CONN_LIFETIME_S = 300.0
_STMT_TIMEOUT_MS = 30000
_READ_ONLY_DEFAULT = False
_APP_NAME = "Zyra"


class DatabaseError(Exception):
    """Base exception for database-related errors."""


class ConnectionError(DatabaseError):
    """Raised when database connection fails."""


class QueryError(DatabaseError):
    """Raised when query execution fails."""


class AsyncDatabase:
    """Thin wrapper around asyncpg.Pool with sane defaults."""

    def __init__(self, dsn: str, *, logger=None) -> None:
        if asyncpg is None:
            raise ImportError("asyncpg is required. Install with: pip install asyncpg")

        self._dsn = dsn
        self._pool: Optional[Pool] = None
        self._closed = False
        self._logger = logger

    async def _init_connection(self, conn: Connection) -> None:
        # Per-connection session settings
        await conn.execute(
            "SET timezone = 'UTC';\n"
            "SET client_encoding = 'UTF8';\n"
            f"SET statement_timeout = {_STMT_TIMEOUT_MS};\n"
            + (
                "SET default_transaction_read_only = on;\n"
                if _READ_ONLY_DEFAULT
                else ""
            )
        )

    async def _pool_ready(self) -> Pool:
        if self._closed:
            raise ConnectionError("Database connection is closed")

        if self._pool is None:
            try:
                self._pool = await asyncpg.create_pool(
                    dsn=self._dsn,
                    min_size=_MIN_SIZE,
                    max_size=_MAX_SIZE,
                    command_timeout=_COMMAND_TIMEOUT_S,
                    max_inactive_connection_lifetime=_MAX_INACTIVE_CONN_LIFETIME_S,
                    init=self._init_connection,
                    server_settings={"application_name": _APP_NAME, "jit": "off"},
                )
                if self._logger:
                    self._logger.info("Database pool initialized")
            except Exception as e:  # pragma: no cover - env specific
                if self._logger:
                    self._logger.error("Failed to create database pool: %s", e)

                raise ConnectionError(f"Failed to create database pool: {e}") from e

        return self._pool

    @asynccontextmanager
    async def acquire(self):
        pool = await self._pool_ready()
        try:
            conn = await asyncio.wait_for(pool.acquire(), timeout=_ACQUIRE_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            raise ConnectionError("Timed out acquiring a database connection") from exc

        try:
            yield conn
        finally:
            await pool.release(conn)

    @asynccontextmanager
    async def transaction(self, *, read_only: Optional[bool] = None):
        async with self.acquire() as conn:
            if read_only is not None:
                await conn.execute(
                    "SET LOCAL default_transaction_read_only = "
                    + ("on" if read_only else "off")
                )

            trx = conn.transaction()
            await trx.start()
            try:
                yield conn
            except Exception:
                with contextlib.suppress(Exception):
                    await trx.rollback()

                raise
            else:
                await trx.commit()

    async def execute(self, q: str, *args: Any, timeout: Optional[float] = None) -> str:
        start = _time.perf_counter_ns()
        try:
            async with self.acquire() as conn:
                return await conn.execute(q, *args, timeout=timeout)
        except Exception as exc:
            raise QueryError(f"Execute failed: {exc}") from exc
        finally:
            self._trace("execute", start, q)

    async def fetch(
        self, q: str, *args: Any, timeout: Optional[float] = None
    ) -> List[Record]:
        start = _time.perf_counter_ns()
        try:
            async with self.acquire() as conn:
                return await conn.fetch(q, *args, timeout=timeout)
        except Exception as exc:
            raise QueryError(f"Fetch failed: {exc}") from exc
        finally:
            self._trace("fetch", start, q)

    async def fetchrow(
        self, q: str, *args: Any, timeout: Optional[float] = None
    ) -> Optional[Record]:
        start = _time.perf_counter_ns()
        try:
            async with self.acquire() as conn:
                return await conn.fetchrow(q, *args, timeout=timeout)
        except Exception as exc:
            raise QueryError(f"Fetchrow failed: {exc}") from exc
        finally:
            self._trace("fetchrow", start, q)

    async def fetchval(
        self, q: str, *args: Any, column: int = 0, timeout: Optional[float] = None
    ) -> Any:
        start = _time.perf_counter_ns()
        try:
            async with self.acquire() as conn:
                return await conn.fetchval(q, *args, column=column, timeout=timeout)
        except Exception as exc:
            raise QueryError(f"Fetchval failed: {exc}") from exc
        finally:
            self._trace("fetchval", start, q)

    async def executemany(
        self,
        q: str,
        args_iter: Iterable[Sequence[Any]],
        *,
        timeout: Optional[float] = None,
    ) -> None:
        start = _time.perf_counter_ns()
        try:
            async with self.acquire() as conn:
                await conn.executemany(q, list(args_iter), timeout=timeout)
        except Exception as exc:
            raise QueryError(f"Executemany failed: {exc}") from exc
        finally:
            self._trace("executemany", start, q)

    async def copy_to_table(
        self,
        table_name: str,
        *,
        source: Union[str, bytes, Iterable],
        columns: Optional[List[str]] = None,
        schema_name: str = "public",
        format: str = "text",
        timeout: Optional[float] = None,
    ) -> str:
        start = _time.perf_counter_ns()
        try:
            async with self.acquire() as conn:
                return await conn.copy_to_table(
                    table_name,
                    source=source,
                    columns=columns,
                    schema_name=schema_name,
                    format=format,
                    timeout=timeout,
                )
        except Exception as exc:
            raise QueryError(f"Copy to table failed: {exc}") from exc
        finally:
            self._trace("copy_to_table", start, table_name)

    async def copy_from_table(
        self,
        table_name: str,
        *,
        output,
        columns: Optional[List[str]] = None,
        schema_name: str = "public",
        format: str = "text",
        timeout: Optional[float] = None,
    ) -> str:
        start = _time.perf_counter_ns()
        try:
            async with self.acquire() as conn:
                return await conn.copy_from_table(
                    table_name,
                    output=output,
                    columns=columns,
                    schema_name=schema_name,
                    format=format,
                    timeout=timeout,
                )
        except Exception as exc:
            raise QueryError(f"Copy from table failed: {exc}") from exc
        finally:
            self._trace("copy_from_table", start, table_name)

    async def health_check(self) -> dict[str, Any]:
        start = _time.perf_counter()
        try:
            v = await self.fetchval("SELECT 1")
            ok = v == 1
            pool = await self._pool_ready()
            info = {
                "size": pool.get_size(),
                "min_size": pool.get_min_size(),
                "max_size": pool.get_max_size(),
                "idle_size": pool.get_idle_size(),
            }
            ver = await self.fetchval("SELECT version()")
            return {
                "status": "healthy" if ok else "degraded",
                "response_ms": round((_time.perf_counter() - start) * 1000, 2),
                "pool": info,
                "version": ver.split(",")[0] if isinstance(ver, str) else "PostgreSQL",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "response_ms": round((_time.perf_counter() - start) * 1000, 2),
            }

    async def close(self) -> None:
        if not self._closed and self._pool:
            await self._pool.close()
            self._pool = None
            self._closed = True
            if self._logger:
                self._logger.info("Database pool closed")

    def _trace(self, op: str, start_ns: int, label: str) -> None:
        dur_us = (_time.perf_counter_ns() - start_ns) // 1000
        if self._logger and self._logger.isEnabledFor(10):  # DEBUG
            trimmed = label.replace("\n", " ")
            if len(trimmed) > 120:
                trimmed = trimmed[:117] + "..."

            self._logger.debug("db.%s %dus %s", op, dur_us, trimmed)


class DatabaseProvider(ZyraBase):
    """Provider mixed into the bot: hardcoded pool config, DSN from config."""

    db: AsyncDatabase

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        section = self.config.get("database") or {}
        dsn = section.get("db_uri")
        if not dsn:
            raise SystemExit("Missing database.db_uri in config")

        self.db = AsyncDatabase(dsn, logger=self.log)
