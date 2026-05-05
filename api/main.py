"""
FastAPI application for Nebula Civitas.

Single service, multiple routers:
  - /api/elections/...     voting resolution + curated demo scenarios
  - /api/preferences/...   preference elicitation (stateless)

Run with: uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.districting import router as districting_router
from .routers.preferences import router as preferences_router
from .routers.voting import router as voting_router

tags_metadata = [
    {
        "name": "elections",
        "description": (
            "Resolve ballots under different voting methods and fetch curated "
            "demo scenarios used by the elections explorer UI."
        ),
    },
    {
        "name": "preferences",
        "description": (
            "Bayesian preference elicitation. Stateless: every request carries "
            "the full PreferenceState; every response returns the updated state."
        ),
    },
    {
        "name": "districting",
        "description": (
            "Algorithmic redistricting. Step 1 ships apportionment "
            "(Method of Equal Proportions on 2020 census populations); the "
            "districting algorithm itself follows in later build steps."
        ),
    },
]

app = FastAPI(
    title="Nebula Civitas API",
    description=(
        "Unified API for voting resolution and preference elicitation. "
        "Part of the Nebula Civitas thesis demo."
    ),
    version="0.2.0",
    openapi_tags=tags_metadata,
)

# CORS — allow the Next.js dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voting_router)
app.include_router(preferences_router)
app.include_router(districting_router)


@app.get("/", tags=["meta"])
def root():
    return {
        "status": "ok",
        "service": "nebula-civitas-api",
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
