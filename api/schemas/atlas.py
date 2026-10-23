"""
Pydantic request/response models for the atlas routes.

A layout is three to five candidates at points in the unit square (y grows
downward, as on screen). Maps come back as strings with one character per
cell, row-major from the top left, so a 64 × 64 map is 4,096 characters.
"""

from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from voting.spatial import DEFAULT_GRID
from voting.types import DEFAULT_TIEBREAK_SEED

from .voting import MethodLiteral

MIN_ATLAS_CANDIDATES = 3
MAX_ATLAS_CANDIDATES = 5

# One letter, so a map spends one character per cell
AtlasCandidateId = Annotated[str, StringConstraints(pattern=r"^[A-E]$")]


class AtlasCandidateSchema(BaseModel):
    id: AtlasCandidateId
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1, description="Grows downward, as on screen.")


class AtlasRequest(BaseModel):
    candidates: list[AtlasCandidateSchema] = Field(
        min_length=MIN_ATLAS_CANDIDATES, max_length=MAX_ATLAS_CANDIDATES
    )
    tiebreak_seed: int = Field(
        default=DEFAULT_TIEBREAK_SEED,
        ge=0,
        le=2**31 - 1,
        description="Seed for each method's tiebreak, as in /profile/resolve.",
    )

    @model_validator(mode="after")
    def _distinct_ids(self) -> Self:
        ids = [c.id for c in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("Candidate IDs repeat")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "candidates": [
                        {"id": "A", "x": 0.5, "y": 0.26},
                        {"id": "B", "x": 0.27, "y": 0.66},
                        {"id": "C", "x": 0.73, "y": 0.66},
                        {"id": "D", "x": 0.5, "y": 0.53},
                    ],
                    "tiebreak_seed": 0,
                }
            ]
        }
    }


class AtlasPointRequest(AtlasRequest):
    cell: int = Field(
        ge=0,
        lt=DEFAULT_GRID * DEFAULT_GRID,
        description="Row-major cell index; its center is where the cloud sits.",
    )


class VoterCloudSchema(BaseModel):
    voters_per_type: int
    spread: float = Field(description="Standard deviation of the Gaussian the cloud approximates.")
    offsets: list[tuple[float, float]] = Field(
        description="Each voter type's offset from the cloud's center, in cloud order."
    )


class AtlasMapSchema(BaseModel):
    method: MethodLiteral
    winners: str = Field(description="The winning candidate's ID in every cell.")
    ties: list[int] = Field(description="Cells where a tiebreak decided the winner.")


class AtlasResponse(BaseModel):
    candidates: list[AtlasCandidateSchema]
    size: int = Field(description="Cells per side.")
    cloud: VoterCloudSchema
    ballot_model: str
    tiebreak_seed: int
    maps: list[AtlasMapSchema] = Field(description="One map per method, in method order.")
    condorcet: str = Field(
        description="The Condorcet winner in every cell, or '-' where there is none."
    )
    utilitarian: str = Field(
        description="The candidate with the least total distance to the voters, in every cell."
    )
    disagreement: str = Field(
        description="How many different winners the seven methods produce, one digit per cell."
    )
