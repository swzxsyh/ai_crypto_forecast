"""Repository factory for configured persistence backend."""

from __future__ import annotations

from crypto_predictor.config import DB_BACKEND
from crypto_predictor.domain.repositories import PredictionRepository
from crypto_predictor.infrastructure.persistence.mysql_repository import MySQLPredictionRepository
from crypto_predictor.infrastructure.persistence.postgres_repository import PostgreSQLPredictionRepository
from crypto_predictor.infrastructure.persistence.sqlite_repository import SQLitePredictionRepository


def get_repository() -> PredictionRepository:
    if DB_BACKEND == "postgresql":
        return PostgreSQLPredictionRepository()
    if DB_BACKEND == "mysql":
        return MySQLPredictionRepository()
    return SQLitePredictionRepository()