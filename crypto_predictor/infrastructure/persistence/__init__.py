"""Persistence adapters."""

from crypto_predictor.infrastructure.persistence.mysql_repository import MySQLPredictionRepository
from crypto_predictor.infrastructure.persistence.postgres_repository import PostgreSQLPredictionRepository
from crypto_predictor.infrastructure.persistence.repository_factory import get_repository
from crypto_predictor.infrastructure.persistence.sqlite_repository import SQLitePredictionRepository

__all__ = [
    "SQLitePredictionRepository",
    "PostgreSQLPredictionRepository",
    "MySQLPredictionRepository",
    "get_repository",
]