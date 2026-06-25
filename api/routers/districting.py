"""
HTTP router for the districting demo.

Step 1 ships only the apportionment endpoint. Endpoints for the districting
algorithm itself (per-state map, national composite) land in step 4+.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from districting import (
    CAP_ANCHORS,
    CACHE_VERSION,
    InvalidApportionmentError,
    POPULAR_STATE_FIPS,
    US_2020_APPORTIONMENT_POPULATIONS,
    US_2020_TOTAL_APPORTIONMENT_POPULATION,
    apportion_us_2020,
    build_precompute_manifest,
)


router = APIRouter(prefix="/api/districting", tags=["districting"])


# ---------------------------------------------------------------------------
# Slider bounds for the demo. Pinned in code (not a runtime parameter) so
# the API contract matches the design doc and the UI can rely on them.
# ---------------------------------------------------------------------------

CAP_MIN: int = 435  # Current US House size, set by the Reapportionment Act of 1929.
CAP_MAX: int = 11_037  # Article I §2 ratio: 1 representative per 30,000 people.


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ApportionmentResponse(BaseModel):
    """Per-state seat counts for a given total House size."""

    cap: int = Field(
        description="Total number of House seats requested.",
        examples=[435, 692, 11037],
    )
    apportionment: dict[str, int] = Field(
        description=(
            "State FIPS code -> seats assigned. Includes all 50 states; "
            "values sum to `cap`."
        ),
    )
    total_states: int = Field(
        description="Number of states in the apportionment (always 50 for v1).",
    )
    total_apportionment_population: int = Field(
        description=(
            "Total 2020 census apportionment population summed across the "
            "50 states. Provided for context (e.g. the UI can display "
            "average district size as total / cap)."
        ),
    )


class PrecomputeJobResponse(BaseModel):
    """One district-plan artifact the system should compute ahead of time."""

    state_fips: str
    cap: int
    seats: int
    cache_key: str
    compute_tier: str


class PrecomputeManifestResponse(BaseModel):
    """Precompute contract for expensive district-plan artifacts."""

    cache_version: str
    cap_anchors: list[int]
    priority_state_fips: list[str]
    jobs: list[PrecomputeJobResponse]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/apportionment",
    response_model=ApportionmentResponse,
    summary="Apportion House seats among the 50 states (Method of Equal Proportions)",
)
def get_apportionment(
    cap: int = Query(
        CAP_MIN,
        ge=CAP_MIN,
        le=CAP_MAX,
        description=(
            f"Total House size. Must be in [{CAP_MIN}, {CAP_MAX}]. "
            f"{CAP_MIN} is the current cap (1929); {CAP_MAX} is the "
            f"Article I §2 ratio of 1 representative per 30,000 people."
        ),
    ),
) -> ApportionmentResponse:
    """
    Return the apportionment of `cap` House seats among the 50 states using
    the Method of Equal Proportions (the rule in current US law) on 2020
    census apportionment populations.

    Sub-millisecond cost; safe to call on every slider tick.
    """
    try:
        seats = apportion_us_2020(total_seats=cap)
    except InvalidApportionmentError as exc:
        # The Query bounds make this unreachable, but raise a proper 422
        # rather than propagating the domain exception if the bounds ever
        # widen and a bad value sneaks through.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ApportionmentResponse(
        cap=cap,
        apportionment=seats,
        total_states=len(US_2020_APPORTIONMENT_POPULATIONS),
        total_apportionment_population=US_2020_TOTAL_APPORTIONMENT_POPULATION,
    )


@router.get(
    "/precompute-manifest",
    response_model=PrecomputeManifestResponse,
    summary="List state/cap district plans that should be precomputed",
)
def get_precompute_manifest() -> PrecomputeManifestResponse:
    """
    Return the first cache manifest for expensive balanced-power district plans.

    The UI can fetch apportionment live, but real district polygons should be
    generated offline, stored by `cache_key`, and served as static artifacts.
    """
    jobs = build_precompute_manifest(apportion_us_2020)
    return PrecomputeManifestResponse(
        cache_version=CACHE_VERSION,
        cap_anchors=list(CAP_ANCHORS),
        priority_state_fips=list(POPULAR_STATE_FIPS),
        jobs=[
            PrecomputeJobResponse(
                state_fips=job.state_fips,
                cap=job.cap,
                seats=job.seats,
                cache_key=job.cache_key,
                compute_tier=job.compute_tier,
            )
            for job in jobs
        ],
    )
