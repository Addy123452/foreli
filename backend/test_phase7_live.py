"""Focused tests for Phase 7 live-data provider interface.

Run from the project root:

    python -m backend.test_phase7_live

All payloads here are CLEARLY MOCK data for contract testing only. Nothing in
this file represents a live provider result.
"""
import os

from backend.live import (
    ProviderNotConfigured,
    fetch_live_matches,
    normalize_match,
    provider_status,
)

# Clearly-labelled MOCK payload (not live).
MOCK_PROVIDER_PAYLOAD = {
    "id": 999,
    "competition": {"name": "Mock Cup"},
    "homeTeam": {"name": "Mock United"},
    "awayTeam": {"name": "Mock Rovers"},
    "status": "FINISHED",
    "score": {"fullTime": {"home": 2, "away": 1}},
    "utcDate": "2026-01-01T12:00:00Z",
    "minute": None,
    "statistics": None,
}


def test_status_not_configured():
    for key in ("FOOTBALL_LIVE_API_KEY", "FOOTBALL_LIVE_API_BASE_URL"):
        os.environ.pop(key, None)
    status = provider_status()
    assert status["configured"] is False
    assert "FOOTBALL_LIVE_API_KEY" in status["required_env"]
    assert "FOOTBALL_LIVE_API_BASE_URL" in status["missing_env"]


def test_fetch_raises_when_unconfigured():
    for key in ("FOOTBALL_LIVE_API_KEY", "FOOTBALL_LIVE_API_BASE_URL"):
        os.environ.pop(key, None)
    try:
        fetch_live_matches()
    except ProviderNotConfigured:
        return
    raise AssertionError("expected ProviderNotConfigured when no provider is set")


def test_normalize_mock_payload():
    match = normalize_match(MOCK_PROVIDER_PAYLOAD)
    assert match["match_id"] == "999"
    assert match["competition"] == "Mock Cup"
    assert match["home_team"] == "Mock United"
    assert match["away_team"] == "Mock Rovers"
    assert match["home_score"] == 2
    assert match["away_score"] == 1
    assert match["status"] == "FINISHED"
    assert match["kickoff_utc"] == "2026-01-01T12:00:00Z"


def test_missing_fields_not_invented():
    match = normalize_match({})
    for field in ("match_id", "home_team", "away_team", "home_score", "away_score", "minute"):
        assert match[field] is None, field


def main():
    for name, fn in [
        ("provider status reports not configured", test_status_not_configured),
        ("fetch raises when unconfigured", test_fetch_raises_when_unconfigured),
        ("normalize MOCK payload", test_normalize_mock_payload),
        ("missing fields are not invented", test_missing_fields_not_invented),
    ]:
        fn()
        print(f"  PASS  {name}")
    print("All Phase 7 live-interface tests passed (mock data only, not live).")


if __name__ == "__main__":
    main()
