"""Prediction domain registry and routing (Phase 6).

Foreli currently implements ONE prediction domain: personal productivity
(deadlines, workload, schedule conflicts, delay risk, completion patterns) via a
transparent rule-based + statistical engine in ``backend/engine.py``.

There is NO sports model, trained dataset, live sports feed, or football
predictor anywhere in this codebase. This registry exists so prediction requests
can be routed to the correct domain model, and unsupported domains (e.g. sports)
are reported honestly instead of returning fabricated predictions.
"""

DOMAINS = {
    "personal": {
        "id": "personal",
        "implemented": True,
        "description": (
            "Personal productivity predictions: deadline/task-overload risk, "
            "schedule conflicts, delay risk, missed-deadline patterns, and "
            "completion-pace changes."
        ),
        "prediction_types": [
            "overload", "workload", "conflict", "delay", "missed", "slowdown",
        ],
        "engine": "backend/engine.py (rule-based + statistical baselines)",
    },
}

# Domains that are known but have NO implementation, model, or data in Foreli.
UNSUPPORTED_DOMAINS = {
    "sports": "No sports model, trained dataset, or live sports feed exists in Foreli.",
    "football": "No football model, trained dataset, or live football feed exists in Foreli.",
    "soccer": "No soccer model, trained dataset, or live soccer feed exists in Foreli.",
    "basketball": "No basketball model, trained dataset, or live feed exists in Foreli.",
}


class UnsupportedDomain(Exception):
    """Raised when a prediction request targets a domain Foreli cannot serve."""

    def __init__(self, domain: str, reason: str):
        self.domain = domain
        self.reason = reason
        super().__init__(f"Prediction domain '{domain}' is not implemented. {reason}")


def resolve_domain(name: str):
    """Return ``(domain_id, config)`` for a supported domain.

    Raises :class:`UnsupportedDomain` for sports, unknown, or empty domains so
    callers can return an honest error instead of fake predictions.
    """
    key = (name or "").strip().lower()
    if key in DOMAINS:
        return key, DOMAINS[key]
    reason = UNSUPPORTED_DOMAINS.get(key, "Unknown prediction domain.")
    raise UnsupportedDomain(key or "(empty)", reason)


def domain_catalog() -> dict:
    """Public catalog of implemented and explicitly unsupported domains."""
    return {
        "implemented": list(DOMAINS.values()),
        "unsupported": UNSUPPORTED_DOMAINS,
        "note": (
            "Only implemented domains can produce predictions. Unsupported "
            "domains are reported, never fabricated."
        ),
    }
