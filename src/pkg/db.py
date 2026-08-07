from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from asyncpg import Connection, Pool, Record, create_pool


class DictRecord(Record):
    def __getattr__(self, name: str) -> Any:
        return self[name]


class DbContext:
    def __init__(self, pool: Pool):
        self._pool = pool

    @property
    def pool(self) -> Pool:
        if not self._pool:
            raise RuntimeError("Connect to db first")

        return self._pool

    async def fetchrow(self, query: str, *args: Any, **kwargs: Any) -> DictRecord:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args, **kwargs)

    async def fetchval(self, query: str, *args: Any, **kwargs: Any) -> Any:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args, **kwargs)

    async def execute(self, query: str, *args: Any, **kwargs: Any) -> None:
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args, **kwargs)

    async def fetch(self, query: str, *args: Any, **kwargs: Any) -> list[DictRecord]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args, **kwargs)

    async def close(self):
        return await self.pool.close()

    @asynccontextmanager
    async def tx(self) -> AsyncGenerator[Connection]:
        """Even shorter alias for transaction context manager."""
        async with self.pool.acquire() as conn, conn.transaction():
            yield conn

    @classmethod
    async def create(cls, uri: str, *args, **kwargs) -> "DbContext":
        pool = await create_pool(dsn=uri)
        return DbContext(pool)
