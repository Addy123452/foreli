"""Live match data provider interface (Phase 7).

Foreli has NO sports prediction pipeline and NO live-data provider configured.
This module defines the provider contract, normalizes provider payloads, and
reports the exact credentials required. It never invents live data: if no
provider is configured, callers receive a clear error instead of fabricated
scores, fixtures, or predictions.
"""
import os

# Exact environment variables required to configure a live provider.
REQUIRED_ENV = ["FOOTBALL_LIVE_API_KEY", "FOOTBALL_LIVE_API_BASE_URL"]


class LiveProviderError(Exception):
    """Base error for live-data operations."""


class ProviderNotConfigured(LiveProviderError):
    """No credentials/provider configured."""


class ProviderAdapterMissing(LiveProviderError):
    """Credentials present but no network adapter has been implemented."""


def normalize_match(raw: dict) -> dict:
    """Normalize a provider match payload into Foreli's canonical shape.

    This is pure field mapping. Missing values are left as ``None`` — nothing is
    imputed or invented.
    """
    raw = raw or {}
    score = raw.get("score") or {}
    full_time = score.get("fullTime") or {}
    competition = raw.get("competition") or {}
    home = raw.get("homeTeam") or {}
    away = raw.get("awayTeam") or {}
    return {
        "match_id": str(raw.get("id")) if raw.get("id") is not None else None,
        "competition": competition.get("name"),
        "home_team": home.get("name"),
        "away_team": away.get("name"),
        "status": raw.get("status"),
        "home_score": full_time.get("home"),
        "away_score": full_time.get("away"),
        "kickoff_utc": raw.get("utcDate"),
        "minute": raw.get("minute"),
        "stats": raw.get("statistics"),
    }


def provider_status() -> dict:
    """Report whether a live provider is configured and what is required."""
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    configured = not missing
    if configured:
        note = "Provider credentials present, but no network adapter is implemented yet."
    else:
        note = (
            "No live match data provider is configured. Foreli has no sports "
            "prediction pipeline; its predictions cover personal productivity only. "
            "Set " + " and ".join(REQUIRED_ENV) + " to enable a provider adapter."
        )
    return {
        "configured": configured,
        "provider": os.environ.get("FOOTBALL_LIVE_API_BASE_URL") if configured else None,
        "required_env": REQUIRED_ENV,
        "missing_env": missing,
        "note": note,
    }


def fetch_live_matches():
    """Return normalized live matches.

    Raises instead of returning fabricated data when no provider is configured or
    no adapter is implemented.
    """
    status = provider_status()
    if not status["configured"]:
        raise ProviderNotConfigured(
            "No live match data provider configured. Required environment variables: "
            + ", ".join(REQUIRED_ENV)
        )
    raise ProviderAdapterMissing(
        "Live provider credentials are set, but no network adapter is implemented. "
        "A real provider integration (HTTP client + response mapping + rate limiting) "
        "must be added before live matches can be returned."
    )
