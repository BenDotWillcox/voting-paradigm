"""Validate and echo an unsaved spectrum session, without statistical inference."""

from preferences.spectrum import (
    InvalidSpectrumHistory as InvalidElicitationHistory,
    load_spectrum_bank,
    validate_spectrum_history,
)

from api.schemas.elicitation import ElicitationRequest, ElicitationResponse


__all__ = ["InvalidElicitationHistory", "run_elicitation"]


def run_elicitation(request: ElicitationRequest) -> ElicitationResponse:
    """Return only the participant's stated answers and the public questions."""
    bank = load_spectrum_bank()
    validate_spectrum_history(request.responses, bank)
    reviewed = len(request.responses)
    return ElicitationResponse(
        bank_version=bank.bank_version,
        questions=bank.questions,
        responses=list(request.responses),
        n_reviewed=reviewed,
        n_answered=sum(item.action == "answer" for item in request.responses),
        n_skipped=sum(item.action == "skip" for item in request.responses),
        n_depends=sum(item.action == "depends" for item in request.responses),
        is_complete=reviewed == len(bank.questions),
    )
