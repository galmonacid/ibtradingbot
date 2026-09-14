"""Fail-closed semantic certification for canonical historical datasets."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date

ALLOWED_EXCLUSION_REASONS = frozenset(
    {"exchange_halt", "not_yet_trading", "post_delisting", "provider_confirmed_missing"}
)


class SemanticCertificationError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class SecurityMembership:
    security_id: str
    effective_from: date
    effective_to: date | None = None


@dataclass(frozen=True, order=True)
class SecurityIdentity:
    security_id: str
    valid_from: date
    valid_to: date | None = None
    delisted: bool = False


@dataclass(frozen=True, order=True)
class CanonicalBar:
    security_id: str
    session: date
    raw_close: float
    adjusted_close: float


@dataclass(frozen=True, order=True)
class CoverageExclusion:
    security_id: str
    session: date
    reason: str


@dataclass(frozen=True, order=True)
class TerminalTreatment:
    security_id: str
    last_tradable_session: date
    disposition: str
    economic_value: float
    source: str


@dataclass(frozen=True, order=True)
class CorporateAction:
    security_id: str
    effective_date: date
    split_ratio: float = 1.0
    cash_dividend: float = 0.0


@dataclass(frozen=True, order=True)
class CertificationFinding:
    code: str
    security_id: str
    session: date | None
    detail: str


@dataclass(frozen=True)
class SemanticCertificationReport:
    passed: bool
    member_session_count: int
    excluded_member_session_count: int
    benchmark_session_count: int
    action_count: int
    findings: tuple[CertificationFinding, ...]

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            default=lambda x: x.isoformat() if isinstance(x, date) else _bad(x),
            sort_keys=True,
            separators=(",", ":"),
        )


def _bad(value: object) -> object:
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _has(start: date, end: date | None, day: date) -> bool:
    return start <= day and (end is None or day < end)


def certify_historical_semantics(
    *,
    sessions: tuple[date, ...],
    memberships: tuple[SecurityMembership, ...],
    identities: tuple[SecurityIdentity, ...],
    bars: tuple[CanonicalBar, ...],
    benchmark_security_id: str,
    exclusions: tuple[CoverageExclusion, ...],
    terminal_treatments: tuple[TerminalTreatment, ...],
    corporate_actions: tuple[CorporateAction, ...],
    factor_relative_tolerance: float = 0.02,
    factor_absolute_tolerance: float = 1e-9,
) -> SemanticCertificationReport:
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise SemanticCertificationError("sessions must be non-empty, unique, and increasing")
    if not benchmark_security_id:
        raise SemanticCertificationError("benchmark_security_id must be non-blank")
    if min(factor_relative_tolerance, factor_absolute_tolerance) < 0:
        raise SemanticCertificationError("factor tolerances must be non-negative")
    f: list[CertificationFinding] = []
    bm: dict[tuple[str, date], CanonicalBar] = {}
    dates: dict[str, list[date]] = {}
    for b in bars:
        k = (b.security_id, b.session)
        if k in bm:
            raise SemanticCertificationError("bars must be unique by security_id and session")
        if not b.security_id or not all(
            math.isfinite(x) and x > 0 for x in (b.raw_close, b.adjusted_close)
        ):
            raise SemanticCertificationError("bars require an identity and positive finite closes")
        bm[k] = b
        dates.setdefault(b.security_id, []).append(b.session)
    ex: dict[tuple[str, date], CoverageExclusion] = {}
    for e in exclusions:
        k = (e.security_id, e.session)
        if k in ex:
            raise SemanticCertificationError("exclusions must be unique by security_id and session")
        if e.reason not in ALLOWED_EXCLUSION_REASONS:
            f.append(
                CertificationFinding(
                    "INVALID_EXCLUSION_REASON", *k, "reason is not an allowed evidenced category"
                )
            )
        if k in bm:
            f.append(CertificationFinding("BAR_AND_EXCLUSION", *k, "bar and exclusion coexist"))
        ex[k] = e
    identity_previous: dict[str, SecurityIdentity] = {}
    for i in sorted(identities, key=lambda x: (x.security_id, x.valid_from)):
        if not i.security_id or i.valid_to is not None and i.valid_to <= i.valid_from:
            raise SemanticCertificationError("invalid identity interval")
        p = identity_previous.get(i.security_id)
        if p is not None and (p.valid_to is None or i.valid_from < p.valid_to):
            f.append(
                CertificationFinding(
                    "OVERLAPPING_IDENTITY",
                    i.security_id,
                    i.valid_from,
                    "identity intervals overlap",
                )
            )
        identity_previous[i.security_id] = i
    active: set[tuple[str, date]] = set()
    count = excluded = 0
    membership_previous: dict[str, SecurityMembership] = {}
    for m in sorted(memberships, key=lambda x: (x.security_id, x.effective_from)):
        if not m.security_id or m.effective_to is not None and m.effective_to <= m.effective_from:
            raise SemanticCertificationError("invalid membership interval")
        membership_prior = membership_previous.get(m.security_id)
        if membership_prior is not None and (
            membership_prior.effective_to is None
            or m.effective_from < membership_prior.effective_to
        ):
            f.append(
                CertificationFinding(
                    "OVERLAPPING_MEMBERSHIP",
                    m.security_id,
                    m.effective_from,
                    "membership intervals overlap",
                )
            )
        membership_previous[m.security_id] = m
        interval: set[tuple[str, date]] = set()
        for day in sessions:
            if not _has(m.effective_from, m.effective_to, day):
                continue
            k = (m.security_id, day)
            active.add(k)
            interval.add(k)
            count += 1
            if (
                sum(
                    i.security_id == m.security_id and _has(i.valid_from, i.valid_to, day)
                    for i in identities
                )
                != 1
            ):
                f.append(
                    CertificationFinding(
                        "MEMBERSHIP_WITHOUT_IDENTITY", *k, "membership lacks exactly one identity"
                    )
                )
            if k in ex:
                excluded += 1
            elif k not in bm:
                f.append(CertificationFinding("MISSING_MEMBER_COVERAGE", *k, "no bar or exclusion"))
        if interval and interval.issubset(ex):
            f.append(
                CertificationFinding(
                    "ALL_MEMBER_DATA_EXCLUDED",
                    m.security_id,
                    m.effective_from,
                    "entire interval excluded",
                )
            )
    for k in sorted(set(ex) - active):
        f.append(CertificationFinding("ORPHAN_EXCLUSION", k[0], k[1], "not active"))
    for day in sessions:
        if (benchmark_security_id, day) not in bm:
            f.append(
                CertificationFinding(
                    "MISSING_BENCHMARK_COVERAGE",
                    benchmark_security_id,
                    day,
                    "benchmark bar missing",
                )
            )
    tm: dict[str, TerminalTreatment] = {}
    for t in terminal_treatments:
        if t.security_id in tm:
            raise SemanticCertificationError("duplicate terminal treatment")
        if t.disposition not in {"cash", "delisting_return", "write_off", "zero"}:
            f.append(
                CertificationFinding(
                    "INVALID_TERMINAL_DISPOSITION",
                    t.security_id,
                    t.last_tradable_session,
                    "unknown disposition",
                )
            )
        if (
            not math.isfinite(t.economic_value)
            or t.economic_value < 0
            or not t.source.strip()
            or (t.disposition == "zero" and t.economic_value != 0)
        ):
            f.append(
                CertificationFinding(
                    "INVALID_TERMINAL_ECONOMICS",
                    t.security_id,
                    t.last_tradable_session,
                    "finite economics and source required",
                )
            )
        tm[t.security_id] = t
    groups: dict[str, list[SecurityIdentity]] = {}
    for i in identities:
        groups.setdefault(i.security_id, []).append(i)
    for sid, rows in groups.items():
        final = max(rows, key=lambda x: x.valid_from)
        if final.valid_to is None and not final.delisted:
            continue
        terminal = tm.get(sid)
        if terminal is None:
            f.append(
                CertificationFinding(
                    "MISSING_TERMINAL_TREATMENT",
                    sid,
                    final.valid_to,
                    "ended stable security lacks treatment",
                )
            )
            continue
        actual = max(dates.get(sid, []), default=None)
        if actual != terminal.last_tradable_session:
            f.append(
                CertificationFinding(
                    "LAST_TRADABLE_BAR_MISMATCH",
                    sid,
                    terminal.last_tradable_session,
                    f"actual is {actual}",
                )
            )
        if final.valid_to is not None and terminal.last_tradable_session >= final.valid_to:
            f.append(
                CertificationFinding(
                    "LAST_BAR_AFTER_IDENTITY_END",
                    sid,
                    terminal.last_tradable_session,
                    "last bar must precede end",
                )
            )
    index = {d: n for n, d in enumerate(sessions)}
    ag: dict[tuple[str, date], list[CorporateAction]] = {}
    for a in corporate_actions:
        if (
            not a.security_id
            or not math.isfinite(a.split_ratio)
            or a.split_ratio <= 0
            or not math.isfinite(a.cash_dividend)
            or a.cash_dividend < 0
        ):
            raise SemanticCertificationError("invalid corporate action")
        ag.setdefault((a.security_id, a.effective_date), []).append(a)
    reconciled: set[tuple[str, date]] = set()
    for (sid, day), aa in sorted(ag.items()):
        n = index.get(day)
        if n is None or n == 0:
            f.append(
                CertificationFinding(
                    "ACTION_WITHOUT_FACTOR_WINDOW", sid, day, "preceding session required"
                )
            )
            continue
        previous_bar = bm.get((sid, sessions[n - 1]))
        current_bar = bm.get((sid, day))
        if previous_bar is None or current_bar is None:
            f.append(
                CertificationFinding("ACTION_WITHOUT_BARS", sid, day, "adjacent bars required")
            )
            continue
        div = sum(a.cash_dividend for a in aa)
        if div >= previous_bar.raw_close:
            f.append(
                CertificationFinding("INVALID_DIVIDEND_FACTOR", sid, day, "dividend exceeds price")
            )
            continue
        observed = (current_bar.adjusted_close / current_bar.raw_close) / (
            previous_bar.adjusted_close / previous_bar.raw_close
        )
        expected = (
            math.prod(a.split_ratio for a in aa)
            * previous_bar.raw_close
            / (previous_bar.raw_close - div)
        )
        if not math.isclose(
            observed, expected, rel_tol=factor_relative_tolerance, abs_tol=factor_absolute_tolerance
        ):
            f.append(
                CertificationFinding(
                    "CORPORATE_ACTION_FACTOR_MISMATCH",
                    sid,
                    day,
                    f"observed {observed:.12g}; expected {expected:.12g}",
                )
            )
        reconciled.add((sid, day))
    for sid, dd in dates.items():
        avail = sorted(set(dd) & set(sessions))
        for pd, cd in zip(avail, avail[1:], strict=False):
            if index[cd] != index[pd] + 1:
                continue
            prior_bar = bm[(sid, pd)]
            next_bar = bm[(sid, cd)]
            ratio = (next_bar.adjusted_close / next_bar.raw_close) / (
                prior_bar.adjusted_close / prior_bar.raw_close
            )
            if (sid, cd) not in reconciled and not math.isclose(
                ratio, 1.0, rel_tol=factor_relative_tolerance, abs_tol=factor_absolute_tolerance
            ):
                f.append(
                    CertificationFinding(
                        "UNEXPLAINED_ADJUSTMENT_FACTOR_CHANGE",
                        sid,
                        cd,
                        f"factor ratio {ratio:.12g}",
                    )
                )
    ff = tuple(
        sorted(
            f,
            key=lambda x: (
                x.code,
                x.security_id,
                "" if x.session is None else x.session.isoformat(),
                x.detail,
            ),
        )
    )
    return SemanticCertificationReport(
        not ff, count, excluded, len(sessions), len(corporate_actions), ff
    )
