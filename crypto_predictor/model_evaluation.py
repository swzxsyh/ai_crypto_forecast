"""Multi-model evaluation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelVote:
    model_type: str
    direction: str
    confidence: int
    position_side: str


@dataclass(frozen=True)
class ModelEvaluation:
    votes: list[ModelVote]
    consensus_direction: str | None
    average_confidence: float | None
    details: dict[str, Any]


def evaluate_prediction_votes(results: list[dict[str, Any]]) -> ModelEvaluation:
    votes: list[ModelVote] = []
    for result in results:
        prediction = result.get("prediction", {})
        votes.append(
            ModelVote(
                model_type=str(result.get("model_type", "")),
                direction=str(prediction.get("direction", "")),
                confidence=int(prediction.get("confidence", 0) or 0),
                position_side=str(prediction.get("position_side", "")),
            )
        )

    if not votes:
        return ModelEvaluation(votes=[], consensus_direction=None, average_confidence=None, details={})

    directions = {vote.direction for vote in votes if vote.direction}
    consensus_direction = directions.pop() if len(directions) == 1 else None
    average_confidence = sum(vote.confidence for vote in votes) / len(votes)
    return ModelEvaluation(
        votes=votes,
        consensus_direction=consensus_direction,
        average_confidence=round(average_confidence, 2),
        details={"models": [vote.model_type for vote in votes]},
    )
