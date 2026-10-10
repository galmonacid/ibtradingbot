"""Compare a native historical universe with the retained development slice."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from src.data.trusted_historical import SecurityMembershipInterval


def _active(rows: Sequence[SecurityMembershipInterval], day: date) -> set[str]:
    result: set[str] = set()
    for row in rows:
        if row.effective_from <= day and (row.effective_to is None or day < row.effective_to):
            if row.security_id in result:
                raise ValueError("overlapping membership intervals")
            result.add(row.security_id)
    return result


def audit_universe(
    decision_dates: Sequence[date],
    native: Sequence[SecurityMembershipInterval],
    retained: Sequence[SecurityMembershipInterval],
    features: Iterable[tuple[str, date, bool]],
    sample_issuer_candidates: Mapping[str, str],
) -> dict[str, Any]:
    """Keep missing histories in the denominator and sample joins explicitly unadmitted.

    Native means the pinned reconstruction, not independent proof of an index's
    historical constituents. No future outcome or present-day ticker map is an input.
    """
    dates = tuple(decision_dates)
    if not dates or dates != tuple(sorted(set(dates))):
        raise ValueError("decision dates must be nonempty, unique and increasing")
    usable: dict[date, set[str]] = {day: set() for day in dates}
    excluded: dict[date, set[str]] = {day: set() for day in dates}
    seen: set[tuple[str, date]] = set()
    for security_id, day, eligible in features:
        if day not in usable:
            continue
        key = (security_id, day)
        if key in seen:
            raise ValueError("duplicate feature key")
        seen.add(key)
        (usable if eligible else excluded)[day].add(security_id)
    monthly = []
    missing_membership: Counter[str] = Counter()
    missing_features: Counter[str] = Counter()
    missing_issuers: Counter[str] = Counter()
    native_ids: set[str] = set()
    for day in dates:
        expected = _active(native, day)
        actual = _active(retained, day)
        if not expected:
            raise ValueError("native universe missing at decision date")
        native_ids.update(expected)
        omitted = expected - actual
        unavailable = expected - usable[day]
        unknown = expected - set(sample_issuer_candidates)
        missing_membership.update(omitted)
        missing_features.update(unavailable)
        missing_issuers.update(unknown)
        monthly.append({
            "date": day.isoformat(), "native_members": len(expected),
            "retained_native_members": len(expected & actual),
            "usable_native_feature_rows": len(expected & usable[day]),
            "excluded_native_feature_rows": len(expected & excluded[day]),
            "native_without_any_feature_row": sorted(expected - usable[day] - excluded[day]),
            "native_without_retained_membership": sorted(omitted),
            "retained_not_native": sorted(actual - expected),
            "usable_features_not_native": sorted(usable[day] - expected),
            "sample_candidate_join_members": len(expected & set(sample_issuer_candidates)),
            "members_without_even_sample_join": len(unknown),
            "admitted_dated_issuer_joins": 0,
        })
    return {
        "contract": "r3-later-universe-coverage-v1",
        "monthly": monthly, "unique_native_security_ids": len(native_ids),
        "native_security_months": sum(row["native_members"] for row in monthly),
        "missing_retained_membership_security_months": sum(missing_membership.values()),
        "missing_usable_feature_security_months": sum(missing_features.values()),
        "without_sample_join_security_months": sum(missing_issuers.values()),
        "remediation_queue": [
            {"security_id": security_id,
             "months_missing_retained_membership": missing_membership[security_id],
             "months_missing_usable_features": missing_features[security_id],
             "months_without_sample_issuer_join": missing_issuers[security_id],
             "candidate_cik": sample_issuer_candidates.get(security_id),
             "candidate_join_admitted": False}
            for security_id in sorted(native_ids,
                                      key=lambda key: (-missing_membership[key], key))
        ],
        "full_universe_enrichment_ready": False,
        "qualification_permitted": False,
        "limitations": [
            "Native reconstruction and inherited identity rules retain their evidence limits.",
            "Sample CIK matches are discovery candidates, not dated issuer/class evidence.",
            "Missing usable features include causal exclusions, not just acquisition failures.",
            "Counts do not measure return bias or establish daily prices/actions completeness.",
        ],
    }


def discover_symbol_candidates(
    symbols: Sequence[str],
    provider_rows: Sequence[Mapping[str, str]],
    sec_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Retain all exact-symbol discovery matches, including reused symbols and ETFs.

    Current catalogues never confer a dated identity, asset classification, verified
    API entitlement or usable historical price coverage. Do not normalize punctuation.
    """
    wanted = set(symbols)
    provider = [dict(row) for row in provider_rows if row.get("ticker") in wanted]
    sec = [dict(row) for row in sec_rows if row.get("ticker") in wanted]
    return {
        "provider_exact_symbol_candidates": provider,
        "sec_current_symbol_candidates": sec,
        "symbols_with_multiple_provider_rows": sorted(
            symbol for symbol in wanted
            if sum(row.get("ticker") == symbol for row in provider) > 1
        ),
        "historical_identity_admitted": False,
        "provider_history_verified": False,
        "usage": "discovery only; verify dated issuer/class and actual response before joining",
    }


def lookup_name_candidates(
    names: Sequence[str], lookup_text: str
) -> dict[str, list[dict[str, str]]]:
    """Exact alphanumeric name discovery; preserve collisions and never infer intervals."""
    def key(name: str) -> str:
        return "".join(character for character in name.upper() if character.isalnum())

    wanted: dict[str, list[str]] = {}
    for name in sorted(set(names)):
        normalized = key(name)
        if normalized:
            wanted.setdefault(normalized, []).append(name)
    result: dict[str, list[dict[str, str]]] = {name: [] for name in names}
    for line in lookup_text.splitlines():
        parts = line.rsplit(":", 2)
        if len(parts) != 3 or parts[2] or len(parts[1]) != 10 or not parts[1].isdigit():
            continue
        source_name, cik, _ = parts
        for name in wanted.get(key(source_name), ()):
            row = {"source_name": source_name, "cik": cik}
            if row not in result[name]:
                result[name].append(row)
    return {name: sorted(rows, key=lambda row: (row["cik"], row["source_name"]))
            for name, rows in sorted(result.items())}
