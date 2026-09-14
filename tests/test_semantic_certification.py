from __future__ import annotations

from datetime import date

from src.data.semantic_certification import (
    CanonicalBar,
    CorporateAction,
    CoverageExclusion,
    SecurityIdentity,
    SecurityMembership,
    TerminalTreatment,
    certify_historical_semantics,
)

SESSIONS = (date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6))


def _bars() -> tuple[CanonicalBar, ...]:
    return (
        *(CanonicalBar("benchmark", session, 300.0, 300.0) for session in SESSIONS),
        CanonicalBar("member", SESSIONS[0], 100.0, 50.0),
        CanonicalBar("member", SESSIONS[1], 50.0, 50.0),
    )


def _certify(**overrides: object):
    values = {
        "sessions": SESSIONS,
        "memberships": (SecurityMembership("member", SESSIONS[0], SESSIONS[2]),),
        "identities": (SecurityIdentity("member", SESSIONS[0], SESSIONS[2], True),),
        "bars": _bars(),
        "benchmark_security_id": "benchmark",
        "exclusions": (),
        "terminal_treatments": (TerminalTreatment("member", SESSIONS[1], "cash", 50.0, "Tiingo"),),
        "corporate_actions": (CorporateAction("member", SESSIONS[1], split_ratio=2.0),),
    }
    values.update(overrides)
    return certify_historical_semantics(**values)  # type: ignore[arg-type]


def test_complete_semantics_pass_and_serialize_stably() -> None:
    report = _certify()
    assert report.passed
    assert report.member_session_count == 2
    assert report.to_json() == _certify(bars=tuple(reversed(_bars()))).to_json()


def test_silent_member_and_benchmark_holes_fail_closed() -> None:
    bars = tuple(
        bar
        for bar in _bars()
        if not (bar.security_id == "member" and bar.session == SESSIONS[0])
        and not (bar.security_id == "benchmark" and bar.session == SESSIONS[2])
    )
    report = _certify(bars=bars, corporate_actions=())
    assert not report.passed
    assert {finding.code for finding in report.findings} >= {
        "MISSING_MEMBER_COVERAGE",
        "MISSING_BENCHMARK_COVERAGE",
    }


def test_explicit_exclusion_requires_reason_and_cannot_mask_existing_bar() -> None:
    exclusions = (
        CoverageExclusion("member", SESSIONS[0], ""),
        CoverageExclusion("member", SESSIONS[1], "exchange_halt"),
    )
    report = _certify(exclusions=exclusions)
    assert not report.passed
    codes = {finding.code for finding in report.findings}
    assert "INVALID_EXCLUSION_REASON" in codes
    assert "BAR_AND_EXCLUSION" in codes


def test_ended_identity_requires_terminal_treatment_and_matching_last_bar() -> None:
    missing = _certify(terminal_treatments=())
    assert "MISSING_TERMINAL_TREATMENT" in {finding.code for finding in missing.findings}
    wrong = _certify(
        terminal_treatments=(TerminalTreatment("member", SESSIONS[0], "cash", 50.0, "Tiingo"),)
    )
    assert "LAST_TRADABLE_BAR_MISMATCH" in {finding.code for finding in wrong.findings}


def test_split_and_dividend_factor_mismatch_is_rejected() -> None:
    bad = _certify(corporate_actions=(CorporateAction("member", SESSIONS[1], 3.0, 1.0),))
    assert not bad.passed
    assert "CORPORATE_ACTION_FACTOR_MISMATCH" in {finding.code for finding in bad.findings}


def test_missing_action_window_and_adjacent_bars_fail_closed() -> None:
    first_session = _certify(corporate_actions=(CorporateAction("member", SESSIONS[0], 2.0),))
    assert "ACTION_WITHOUT_FACTOR_WINDOW" in {finding.code for finding in first_session.findings}
    missing_bar = _certify(
        bars=tuple(
            bar
            for bar in _bars()
            if not (bar.security_id == "member" and bar.session == SESSIONS[1])
        )
    )
    assert "ACTION_WITHOUT_BARS" in {finding.code for finding in missing_bar.findings}


def test_alias_rename_is_not_a_terminal_security_event() -> None:
    report = _certify(
        identities=(
            SecurityIdentity("member", SESSIONS[0], SESSIONS[1]),
            SecurityIdentity("member", SESSIONS[1]),
        ),
        terminal_treatments=(),
    )
    assert report.passed


def test_overlap_missing_identity_orphan_and_all_excluded_fail_closed() -> None:
    report = _certify(
        identities=(),
        memberships=(
            SecurityMembership("member", SESSIONS[0], SESSIONS[2]),
            SecurityMembership("member", SESSIONS[1]),
        ),
        bars=tuple(bar for bar in _bars() if bar.security_id != "member"),
        exclusions=tuple(
            CoverageExclusion("member", session, "provider_confirmed_missing")
            for session in SESSIONS[:2]
        )
        + (CoverageExclusion("orphan", SESSIONS[0], "exchange_halt"),),
        terminal_treatments=(),
        corporate_actions=(),
    )
    codes = {finding.code for finding in report.findings}
    assert {
        "OVERLAPPING_MEMBERSHIP",
        "MEMBERSHIP_WITHOUT_IDENTITY",
        "ORPHAN_EXCLUSION",
        "ALL_MEMBER_DATA_EXCLUDED",
    } <= codes


def test_combined_actions_reconcile_and_unexplained_change_fails() -> None:
    changed = tuple(
        CanonicalBar(
            bar.security_id,
            bar.session,
            bar.raw_close,
            50.505050505
            if bar.security_id == "member" and bar.session == SESSIONS[1]
            else bar.adjusted_close,
        )
        for bar in _bars()
    )
    combined = _certify(
        bars=changed,
        corporate_actions=(
            CorporateAction("member", SESSIONS[1], split_ratio=2.0),
            CorporateAction("member", SESSIONS[1], cash_dividend=1.0),
        ),
    )
    assert combined.passed
    unexplained = _certify(bars=changed, corporate_actions=())
    assert "UNEXPLAINED_ADJUSTMENT_FACTOR_CHANGE" in {
        finding.code for finding in unexplained.findings
    }
