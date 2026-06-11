"""Database backend selection boundary.

The current application still uses the function-based SQLite repository in
`crypto_predictor.database`. This module documents and centralizes the switch
point for a future repository implementation such as PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crypto_predictor.config import DB_BACKEND, DB_PATH, POSTGRES_DSN


class DatabaseBackend(Protocol):
    name: str

    def describe(self) -> dict[str, str]:
        ...


@dataclass(frozen=True)
class SQLiteBackend:
    path: str = DB_PATH
    name: str = "sqlite"

    def describe(self) -> dict[str, str]:
        return {"backend": self.name, "path": self.path}


@dataclass(frozen=True)
class PostgreSQLBackend:
    dsn: str = POSTGRES_DSN
    name: str = "postgresql"

    def describe(self) -> dict[str, str]:
        return {"backend": self.name, "dsn": self.dsn}


def get_database_backend() -> DatabaseBackend:
    if DB_BACKEND == "postgresql":
        return PostgreSQLBackend()
    return SQLiteBackend()
