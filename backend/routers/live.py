"""Live match data endpoints (Phase 7).

No live data provider is configured in Foreli. These endpoints report that
honestly and identify the exact credentials required. They never fabricate
scores, fixtures, or predictions.
"""
from fastapi import APIRouter, HTTPException

from ..live import (
    ProviderAdapterMissing,
    ProviderNotConfigured,
    fetch_live_matches,
    provider_status,
)

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/status")
def status():
    """Report live-provider configuration and required credentials."""
    return provider_status()


@router.get("/matches")
def matches():
    """Return normalized live matches, or an honest error if unavailable."""
    try:
        return fetch_live_matches()
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderAdapterMissing as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
