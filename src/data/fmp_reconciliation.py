"""Supplemental FMP checks that can quarantine, but never repair, canonical history."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date

from src.data.canonical_historical import CanonicalCorporateAction, CanonicalDailyBar


class FmpReconciliationError(ValueError):
    """Raised when supplemental evidence is incomplete or internally invalid."""


_FMP_RECONCILIATION_ATTESTATION = object()


@dataclass(frozen=True, order=True)
class FmpPriceObservation:
    security_id: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True, order=True)
class FmpDividendObservation:
    security_id: str
    date: date
    cash_amount: float


@dataclass(frozen=True, order=True)
class FmpDelistingObservation:
    security_id: str
    delisted_on: date
    exchange: str


@dataclass(frozen=True, order=True)
class SupplementalQuarantine:
    check: str
    security_id: str
    date: date
    reason: str


@dataclass(frozen=True, order=True)
class FmpFinding:
    check: str
    security_id: str
    date: date
    detail: str
    quarantined: bool


@dataclass(frozen=True)
class FmpReconciliationReport:
    canonical_bars_sha256: str
    canonical_actions_sha256: str
    price_observations: int
    dividend_observations: int
    delisting_observations: int
    findings: tuple[FmpFinding, ...]
    passed: bool
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _FMP_RECONCILIATION_ATTESTATION:
            raise FmpReconciliationError(
                "FMP reports must be issued by the concrete reconciliation function"
            )


def _digest(rows: object) -> str:
    return hashlib.sha256(
        json.dumps(rows, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _close(left: float, right: float, tolerance: float) -> bool:
    return math.isclose(left, right, rel_tol=tolerance, abs_tol=tolerance)


def reconcile_fmp_supplemental(
    *,
    canonical_bars: tuple[CanonicalDailyBar, ...],
    canonical_actions: tuple[CanonicalCorporateAction, ...],
    prices: tuple[FmpPriceObservation, ...],
    dividends: tuple[FmpDividendObservation, ...],
    delistings: tuple[FmpDelistingObservation, ...],
    quarantines: tuple[SupplementalQuarantine, ...] = (),
    price_tolerance: float = 1e-4,
    dividend_tolerance: float = 1e-6,
) -> FmpReconciliationReport:
    """Compare FMP observations without using them to add or alter canonical records."""
    if not prices:
        raise FmpReconciliationError("FMP price observations must be represented")
    if price_tolerance < 0 or dividend_tolerance < 0:
        raise FmpReconciliationError("reconciliation tolerances must be nonnegative")
    quarantine_keys: set[tuple[str, str, date]] = set()
    for item in quarantines:
        if item.check not in {"price", "dividend", "delisting"} or not item.reason.strip():
            raise FmpReconciliationError("supplemental quarantine is invalid")
        key = (item.check, item.security_id, item.date)
        if key in quarantine_keys:
            raise FmpReconciliationError("duplicate supplemental quarantine")
        quarantine_keys.add(key)

    bar_by_key = {(row.security_id, row.date): row for row in canonical_bars}
    action_by_key = {
        (row.action_type, row.security_id, row.action_date): row for row in canonical_actions
    }
    findings: list[FmpFinding] = []

    def finding(check: str, security_id: str, day: date, detail: str) -> None:
        findings.append(
            FmpFinding(
                check,
                security_id,
                day,
                detail,
                (check, security_id, day) in quarantine_keys,
            )
        )

    seen: set[tuple[str, str, date]] = set()
    for price_row in prices:
        key = ("price", price_row.security_id, price_row.date)
        if key in seen:
            raise FmpReconciliationError("duplicate FMP price observation")
        seen.add(key)
        if (
            price_row.volume < 0
            or any(
                not math.isfinite(value) or value <= 0
                for value in (price_row.open, price_row.high, price_row.low, price_row.close)
            )
            or price_row.low > min(price_row.open, price_row.close)
            or price_row.high < max(price_row.open, price_row.close)
        ):
            raise FmpReconciliationError("invalid FMP price observation")
        canonical_bar = bar_by_key.get((price_row.security_id, price_row.date))
        if canonical_bar is None:
            finding("price", price_row.security_id, price_row.date, "canonical raw bar is missing")
        elif (
            not all(
                _close(left, right, price_tolerance)
                for left, right in (
                    (canonical_bar.open, price_row.open),
                    (canonical_bar.high, price_row.high),
                    (canonical_bar.low, price_row.low),
                    (canonical_bar.close, price_row.close),
                )
            )
            or canonical_bar.volume != price_row.volume
        ):
            finding("price", price_row.security_id, price_row.date, "raw OHLCV differs from FMP")

    for dividend_row in dividends:
        key = ("dividend", dividend_row.security_id, dividend_row.date)
        if key in seen:
            raise FmpReconciliationError("duplicate FMP dividend observation")
        seen.add(key)
        if not math.isfinite(dividend_row.cash_amount) or dividend_row.cash_amount < 0:
            raise FmpReconciliationError("invalid FMP dividend observation")
        canonical_action = action_by_key.get(
            ("dividend", dividend_row.security_id, dividend_row.date)
        )
        if canonical_action is None:
            finding(
                "dividend",
                dividend_row.security_id,
                dividend_row.date,
                "canonical dividend is missing",
            )
        elif not _close(canonical_action.value, dividend_row.cash_amount, dividend_tolerance):
            finding(
                "dividend",
                dividend_row.security_id,
                dividend_row.date,
                "dividend amount differs from FMP",
            )

    for delisting_row in delistings:
        key = ("delisting", delisting_row.security_id, delisting_row.delisted_on)
        if key in seen:
            raise FmpReconciliationError("duplicate FMP delisting observation")
        seen.add(key)
        if not delisting_row.exchange.strip():
            raise FmpReconciliationError("FMP delisting exchange must be recorded")
        canonical_action = action_by_key.get(
            ("delisting", delisting_row.security_id, delisting_row.delisted_on)
        )
        if canonical_action is None:
            finding(
                "delisting",
                delisting_row.security_id,
                delisting_row.delisted_on,
                "canonical delisting is missing",
            )

    expected_price_keys = {("price", row.security_id, row.date) for row in canonical_bars}
    observed_price_keys = {key for key in seen if key[0] == "price"}
    if observed_price_keys != expected_price_keys:
        raise FmpReconciliationError("FMP price observations do not cover every canonical bar")
    for action_type in ("dividend", "delisting"):
        expected_action_keys = {
            (action_type, row.security_id, row.action_date)
            for row in canonical_actions
            if row.action_type == action_type
        }
        observed_action_keys = {key for key in seen if key[0] == action_type}
        if observed_action_keys != expected_action_keys:
            raise FmpReconciliationError(
                f"FMP {action_type} observations do not cover every canonical action"
            )

    finding_keys = {(row.check, row.security_id, row.date) for row in findings}
    if not quarantine_keys.issubset(finding_keys):
        raise FmpReconciliationError("quarantine does not correspond to an observed discrepancy")
    ordered = tuple(sorted(findings))
    return FmpReconciliationReport(
        _digest([asdict(row) for row in canonical_bars]),
        _digest([asdict(row) for row in canonical_actions]),
        len(prices),
        len(dividends),
        len(delistings),
        ordered,
        all(row.quarantined for row in ordered),
        _FMP_RECONCILIATION_ATTESTATION,
    )
