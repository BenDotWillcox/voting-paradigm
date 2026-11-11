"""Map typed expressive-ballot HTTP inputs to pure domain computations."""

from api.schemas.expressive import (
    AllocationSchema,
    BudgetPreviewRequest,
    BudgetPreviewResponse,
    CategoryScoresSchema,
    FundingIssueSchema,
    TransferPreviewSchema,
)
from expressive import FUND_ID, FUND_TOTAL, MODEL_VERSION, BudgetBallot, Flexibility, Transfer, preview_transfer


def preview_budget_transfers(request: BudgetPreviewRequest) -> BudgetPreviewResponse:
    ballot = BudgetBallot(
        ideal=request.ideal.as_mapping(),
        flexibility={
            category: Flexibility(decrease=widths.decrease, increase=widths.increase)
            for category, widths in request.flexibility.as_mapping().items()
        },
    )
    previews: list[TransferPreviewSchema] = []
    for proposal in request.transfers:
        preview = preview_transfer(
            ballot,
            Transfer(source=proposal.source, target=proposal.target, amount=proposal.amount),
        )
        previews.append(TransferPreviewSchema(
            source=proposal.source,
            target=proposal.target,
            amount=proposal.amount,
            allocation=AllocationSchema.model_validate(dict(preview.allocation)),
            feasible=preview.evaluation.feasible,
            funding_issues=[FundingIssueSchema(
                category=issue.category,
                kind=issue.kind,
                required_share=issue.required_share,
                actual_share=issue.actual_share,
            ) for issue in preview.evaluation.funding_issues],
            score=preview.evaluation.score,
            category_scores=(
                CategoryScoresSchema.model_validate(dict(preview.evaluation.category_scores))
                if preview.evaluation.category_scores is not None else None
            ),
        ))
    return BudgetPreviewResponse(model=MODEL_VERSION, fund_id=FUND_ID, fund_total=FUND_TOTAL, previews=previews)
