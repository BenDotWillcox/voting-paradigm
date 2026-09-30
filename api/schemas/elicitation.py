"""Typed envelopes for an unsaved, descriptive spectrum session."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from preferences.spectrum import (
    TARGET_QUESTIONS,
    ReviewedResponse,
    SpectrumQuestion,
)


class ElicitationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ElicitationRequest(ElicitationSchema):
    bank_version: Literal["spectrum_demo_v1"]
    responses: list[ReviewedResponse] = Field(
        default_factory=list, max_length=TARGET_QUESTIONS
    )


class ElicitationResponse(ElicitationSchema):
    bank_version: Literal["spectrum_demo_v1"]
    questions: tuple[SpectrumQuestion, ...] = Field(
        min_length=TARGET_QUESTIONS, max_length=TARGET_QUESTIONS
    )
    responses: list[ReviewedResponse] = Field(max_length=TARGET_QUESTIONS)
    n_reviewed: int = Field(ge=0, le=TARGET_QUESTIONS)
    n_answered: int = Field(ge=0, le=TARGET_QUESTIONS)
    n_skipped: int = Field(ge=0, le=TARGET_QUESTIONS)
    n_depends: int = Field(ge=0, le=TARGET_QUESTIONS)
    target_questions: Literal[4] = TARGET_QUESTIONS
    is_complete: bool
