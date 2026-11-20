"""Private server-to-server forecast route; the caller owns the journal."""

import hmac
import os
from ipaddress import ip_address

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from preferences.journal_forecast import (
    Forecast, JournalRequest, ProviderError, local_model_forecast, wording_forecast,
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


@router.post("/forecast", response_model=Forecast, include_in_schema=False)
async def forecast(request: Request, response: Response) -> Forecast:
    require_local_journal(request)
    try:
        req = JournalRequest.model_validate_json(await request.body())
    except ValidationError:
        # FastAPI's default validation errors can include raw ballot text and votes.
        raise HTTPException(422, "The journal forecast request is invalid.") from None
    response.headers["Cache-Control"] = "no-store"
    mode = os.getenv("PERSONAL_JOURNAL_MODEL_MODE", "baseline")
    if mode == "baseline":
        return await run_in_threadpool(wording_forecast, req)
    if mode != "llm":
        raise HTTPException(503, "Unknown local journal model mode.")
    try:
        return await run_in_threadpool(local_model_forecast, req)
    except ProviderError as error:
        raise HTTPException(502, str(error)) from None
