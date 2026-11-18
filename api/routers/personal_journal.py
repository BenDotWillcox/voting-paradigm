"""Private server-to-server forecast route; the caller owns the journal."""

import hmac
import os
from ipaddress import ip_address
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from preferences.journal_forecast import (
    Forecast, JournalRequest, ProviderError, local_model_forecast, wording_forecast,
)
from preferences.journal_reasoning import (
    HistoryRequest, PairedForecast, Profile, QuestionRequest, QuestionResult, paired_forecast,
    profile, question, reasoning_forecast,
)


def require_local_journal(request: Request) -> None:
    secret = os.getenv("PERSONAL_JOURNAL_API_TOKEN", "")
    if (
        os.getenv("PERSONAL_JOURNAL_LOCAL") != "1"
        or os.getenv("NODE_ENV") == "production"
        or not secret
    ):
        raise HTTPException(404, "Not found")
    try:
        local = request.client is not None and ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    token = request.headers.get("x-journal-token", "")
    if not local or not hmac.compare_digest(secret.encode(), token.encode()):
        raise HTTPException(403, "Local journal access required")


router = APIRouter(prefix="/api/preferences/journal", tags=["preferences"])


Payload = TypeVar("Payload", bound=BaseModel)


async def private_input(request: Request, response: Response, schema: type[Payload]) -> Payload:
    require_local_journal(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        return schema.model_validate_json(await request.body())
    except ValidationError:
        # FastAPI's default validation errors can include raw ballot text and votes.
        raise HTTPException(422, "The journal request is invalid.") from None


@router.post("/forecast", response_model=Forecast, include_in_schema=False)
async def forecast(request: Request, response: Response) -> Forecast:
    req = await private_input(request, response, JournalRequest)
    mode = os.getenv("PERSONAL_JOURNAL_MODEL_MODE", "reasoning")
    if mode == "reasoning":
        return await run_in_threadpool(reasoning_forecast, req)
    if mode == "baseline":
        return await run_in_threadpool(wording_forecast, req)
    if mode != "llm":
        raise HTTPException(503, "Unknown local journal model mode.")
    try:
        return await run_in_threadpool(local_model_forecast, req)
    except ProviderError as error:
        raise HTTPException(502, str(error)) from None


@router.post("/paired", response_model=PairedForecast, include_in_schema=False)
async def paired(request: Request, response: Response) -> PairedForecast:
    req = await private_input(request, response, JournalRequest)
    try:
        return await run_in_threadpool(paired_forecast, req)
    except Exception:
        # A partial comparison is unusable. Model errors can contain private input.
        raise HTTPException(500, "The model comparison could not be computed.") from None


@router.post("/profile", response_model=Profile, include_in_schema=False)
async def preference_profile(request: Request, response: Response) -> Profile:
    req = await private_input(request, response, HistoryRequest)
    return await run_in_threadpool(profile, req)


@router.post("/question", response_model=QuestionResult, response_model_exclude_unset=True, include_in_schema=False)
async def follow_up_question(request: Request, response: Response) -> QuestionResult:
    req = await private_input(request, response, QuestionRequest)
    # Omit an empty optional reference while keeping the required question:null.
    return await run_in_threadpool(question, req)
