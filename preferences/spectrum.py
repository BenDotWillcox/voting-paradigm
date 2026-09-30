"""Public spectrum questions and self-reported answers, without inference.

Position, reported uncertainty, and acceptability are separate observations.
They are not pairwise evidence and are not passed to either utility model.
"""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BANK_VERSION: Final = "spectrum_demo_v1"
TARGET_QUESTIONS: Final = 4
PUBLIC_SPECTRUM_BANK_PATH: Final = (
    Path(__file__).parent / "data" / "spectrum_demo_v1.json"
)
FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]
QuestionId = Annotated[str, Field(min_length=1, max_length=100)]


class SpectrumRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportedUncertainty(SpectrumRecord):
    """Illustrative Gaussian kernel width as a fraction of the full axis span.

    This is the participant's continuous width control, not a calibrated model
    confidence or the measured standard deviation of the bounded drawn curve.
    """

    sd_fraction: float = Field(
        ge=0.08, le=0.28, strict=True, allow_inf_nan=False
    )


class SpectrumAnchor(SpectrumRecord):
    value: FiniteNumber
    label: str = Field(min_length=1)


class SpectrumScale(SpectrumRecord):
    min: FiniteNumber
    max: FiniteNumber
    step: Annotated[float, Field(gt=0.0, strict=True, allow_inf_nan=False)]
    unit: str = Field(min_length=1)
    format: Literal["number", "clock_hour"]
    anchors: tuple[SpectrumAnchor, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def require_ordered_scale(self) -> Self:
        if self.min >= self.max:
            raise ValueError("spectrum scale must have increasing bounds")
        values = [anchor.value for anchor in self.anchors]
        if values != sorted(set(values)):
            raise ValueError("spectrum anchors must be distinct and increasing")
        if values[0] != self.min or values[-1] != self.max:
            raise ValueError("spectrum anchors must include both endpoints")
        for value in values:
            if not self.contains_step(value):
                raise ValueError("spectrum anchors must fall on the scale grid")
        return self

    def contains_step(self, value: float) -> bool:
        """Check the authored decimal grid, without near-step rounding."""
        if not self.min <= value <= self.max:
            return False
        offset = Decimal(str(value)) - Decimal(str(self.min))
        return offset % Decimal(str(self.step)) == 0


class SpectrumQuestion(SpectrumRecord):
    id: QuestionId
    version: Literal[1]
    title: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    context: str = Field(min_length=1)
    scale: SpectrumScale


class SpectrumBank(SpectrumRecord):
    bank_version: Literal["spectrum_demo_v1"]
    questions: tuple[SpectrumQuestion, ...] = Field(
        min_length=TARGET_QUESTIONS, max_length=TARGET_QUESTIONS
    )

    @model_validator(mode="after")
    def require_distinct_questions(self) -> Self:
        if len({question.id for question in self.questions}) != len(self.questions):
            raise ValueError("spectrum question ids must be distinct")
        return self


class AcceptableRange(SpectrumRecord):
    lower: FiniteNumber
    upper: FiniteNumber

    @model_validator(mode="after")
    def require_ordered_bounds(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("acceptable range must have ordered endpoints")
        return self


class QuestionResponse(SpectrumRecord):
    question_id: QuestionId
    question_version: Literal[1]

    @field_validator("question_version", mode="before")
    @classmethod
    def require_integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("question version must be an integer")
        return value


class AnswerResponse(QuestionResponse):
    action: Literal["answer"]
    position: FiniteNumber
    reported_uncertainty: ReportedUncertainty | None = None
    acceptable_range: AcceptableRange | None = None


class NonAnswerResponse(QuestionResponse):
    """Skip and depends are recorded distinctly, without position evidence."""

    action: Literal["skip", "depends"]


ReviewedResponse = Annotated[
    AnswerResponse | NonAnswerResponse, Field(discriminator="action")
]


class InvalidSpectrumHistory(ValueError):
    """A response is outside the versioned question sequence or scale."""


@lru_cache(maxsize=1)
def load_spectrum_bank() -> SpectrumBank:
    """Cache only the immutable public question bank, never participant answers."""
    return SpectrumBank.model_validate_json(
        PUBLIC_SPECTRUM_BANK_PATH.read_text(encoding="utf-8")
    )


def validate_spectrum_history(
    responses: list[ReviewedResponse], bank: SpectrumBank
) -> None:
    if len(responses) > len(bank.questions):
        raise InvalidSpectrumHistory("response history does not match this session")
    for response, question in zip(responses, bank.questions):
        if (response.question_id, response.question_version) != (
            question.id, question.version
        ):
            raise InvalidSpectrumHistory(
                "response history does not match this session"
            )
        if isinstance(response, AnswerResponse):
            positions = [response.position]
            if response.acceptable_range is not None:
                positions.extend(
                    [response.acceptable_range.lower, response.acceptable_range.upper]
                )
            if not all(question.scale.contains_step(value) for value in positions):
                raise InvalidSpectrumHistory(
                    "response values must match the question scale"
                )
