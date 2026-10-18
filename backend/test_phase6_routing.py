"""Focused tests for Phase 6 prediction-domain routing.

Run from the project root:

    python -m backend.test_phase6_routing

No pytest/httpx required. HTTP-level behaviour is checked separately against the
running server (routing, unsupported sports, invalid input, personal path).
"""
from backend.domains import UnsupportedDomain, domain_catalog, resolve_domain


def test_supported():
    domain_id, config = resolve_domain("personal")
    assert domain_id == "personal"
    assert config["implemented"] is True
    assert "overload" in config["prediction_types"]
    # Case / whitespace insensitive routing.
    assert resolve_domain("  PERSONAL ")[0] == "personal"


def test_unsupported_sports():
    for sport in ("sports", "football", "soccer", "basketball"):
        try:
            resolve_domain(sport)
        except UnsupportedDomain as exc:
            assert exc.domain == sport
            assert "not implemented" in str(exc).lower()
        else:
            raise AssertionError(f"{sport!r} should be unsupported")


def test_invalid():
    for bad in ("", "   ", "crypto", "weather"):
        try:
            resolve_domain(bad)
        except UnsupportedDomain:
            pass
        else:
            raise AssertionError(f"{bad!r} should be unsupported")


def test_catalog():
    cat = domain_catalog()
    ids = {d["id"] for d in cat["implemented"]}
    assert ids == {"personal"}, ids
    assert "football" in cat["unsupported"]
    assert "sports" in cat["unsupported"]


def main():
    for name, fn in [
        ("supported personal domain", test_supported),
        ("unsupported sports domains", test_unsupported_sports),
        ("invalid / unknown domains", test_invalid),
        ("domain catalog", test_catalog),
    ]:
        fn()
        print(f"  PASS  {name}")
    print("All Phase 6 routing tests passed.")


if __name__ == "__main__":
    main()
