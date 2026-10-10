from datetime import date

import pytest

from src.data.trusted_historical import SecurityMembershipInterval as Interval
from src.research.r3_universe_coverage import audit_universe

D1 = date(2020, 1, 31)
D2 = date(2020, 2, 28)


def test_missing_history_stays_in_denominator_and_join_is_unadmitted() -> None:
    native = (Interval("source", "a", D1, None), Interval("source", "b", D1, None))
    report = audit_universe((D1, D2), native, native[:1],
                            (("a", D1, True), ("a", D2, False)), {"a": "0000000001"})
    assert report["native_security_months"] == 4
    assert report["missing_retained_membership_security_months"] == 2
    assert report["missing_usable_feature_security_months"] == 3
    assert report["monthly"][0]["native_without_any_feature_row"] == ["b"]
    assert report["monthly"][1]["excluded_native_feature_rows"] == 1
    assert report["monthly"][0]["admitted_dated_issuer_joins"] == 0
    assert report["remediation_queue"][0]["security_id"] == "b"
    assert not report["full_universe_enrichment_ready"]


def test_half_open_membership_and_future_addition() -> None:
    native = (Interval("source", "a", D1, D2), Interval("source", "b", D2, None))
    report = audit_universe((D1, D2), native, native, (), {})
    assert report["monthly"][0]["native_without_any_feature_row"] == ["a"]
    assert report["monthly"][1]["native_without_any_feature_row"] == ["b"]
    prefix = audit_universe((D1,), native[:1], native[:1], (), {})
    assert prefix["monthly"][0] == report["monthly"][0]


def test_extra_retained_members_are_not_counted_as_coverage() -> None:
    native = (Interval("source", "a", D1, None),)
    retained = (Interval("source", "b", D1, None),)
    report = audit_universe((D1,), native, retained, (("b", D1, True),), {})
    assert report["monthly"][0]["usable_native_feature_rows"] == 0
    assert report["monthly"][0]["retained_not_native"] == ["b"]
    assert report["monthly"][0]["usable_features_not_native"] == ["b"]


def test_duplicate_feature_fails() -> None:
    native = (Interval("source", "a", D1, None),)
    with pytest.raises(ValueError, match="duplicate"):
        audit_universe((D1,), native, native, (("a", D1, True), ("a", D1, False)), {})


def test_overlapping_membership_fails() -> None:
    native = (Interval("source", "a", D1, None),) * 2
    with pytest.raises(ValueError, match="overlapping"):
        audit_universe((D1,), native, (), (), {})


def test_missing_native_universe_fails() -> None:
    with pytest.raises(ValueError, match="native universe missing"):
        audit_universe((D1,), (), (), (), {})


@pytest.mark.parametrize("dates", [(), (D2, D1), (D1, D1)])
def test_invalid_dates_fail(dates: tuple[date, ...]) -> None:
    with pytest.raises(ValueError, match="unique and increasing"):
        audit_universe(dates, (), (), (), {})


def test_discovery_preserves_reuse_and_does_not_normalize_classes() -> None:
    from src.research.r3_universe_coverage import discover_symbol_candidates

    provider = [
        {"ticker": "FB", "assetType": "ETF"},
        {"ticker": "BNY", "assetType": "ETF"},
        {"ticker": "BNY", "assetType": "Stock"},
        {"ticker": "BRK-B", "assetType": "Stock"},
    ]
    result = discover_symbol_candidates(("FB", "BNY", "BRK.B"), provider,
                                        [{"ticker": "BNY", "cik_str": 1}])
    assert len(result["provider_exact_symbol_candidates"]) == 3
    assert result["symbols_with_multiple_provider_rows"] == ["BNY"]
    assert not result["historical_identity_admitted"]
    assert not result["provider_history_verified"]


def test_name_lookup_preserves_ambiguity_and_rejects_bad_identifiers() -> None:
    from src.research.r3_universe_coverage import lookup_name_candidates

    found = lookup_name_candidates(
        ("Example Inc.", "", "A:B"),
        "EXAMPLE INC:0000000001:\nExample Inc.:0000000002:\n"
        "EXAMPLE INC:12:\n:0000000003:\nA:B:0000000004:\n",
    )
    assert [row["cik"] for row in found["Example Inc."]] == ["0000000001", "0000000002"]
    assert found[""] == []
    assert found["A:B"] == [{"source_name": "A:B", "cik": "0000000004"}]
