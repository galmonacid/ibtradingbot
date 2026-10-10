"""Causal, period-aligned SEC ratios for offline coverage research.

Issuer-level calculations do not admit a security join or establish model readiness.
No fitted transform, cross-sectional imputation or historical backfill occurs here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from src.research.r3_source_feasibility import Fact

VERSION = "r3-sec-period-aligned-ratios-v1"


@dataclass(frozen=True)
class FactChoice:
    fact: Fact | None
    reason: str | None


def choose_fact(
    facts: tuple[Fact, ...], *, cik: str, concept: str,
    kind: Literal["instant", "annual"], decision_at: datetime,
    period_end: date | None = None, stale_days: int = 550,
) -> FactChoice:
    """Choose the latest available context, failing closed on same-period ambiguity."""
    if decision_at.utcoffset() is None or stale_days < 0:
        raise ValueError("aware decision timestamp and nonnegative stale limit required")
    if any(row.cik != cik for row in facts):
        raise ValueError("facts must belong to one declared issuer")
    eligible = []
    for row in facts:
        if row.accepted_at.utcoffset() is None or row.available_at.utcoffset() is None:
            raise ValueError("fact timestamps must be timezone-aware")
        if row.available_at < row.accepted_at:
            raise ValueError("availability precedes filing acceptance")
        if (row.concept == concept and row.taxonomy == "us-gaap" and row.unit == "USD"
                and row.period_kind == kind and row.available_at <= decision_at
                and row.period_end <= decision_at.date()
                and (period_end is None or row.period_end == period_end)
                and math.isfinite(row.value)):
            eligible.append(row)
    if not eligible:
        return FactChoice(None, "missing_available_usd_context")
    latest_period = max(row.period_end for row in eligible)
    if (decision_at.date() - latest_period).days > stale_days:
        return FactChoice(None, "stale_fiscal_period")
    period_rows = [row for row in eligible if row.period_end == latest_period]
    latest_acceptance = max(row.accepted_at for row in period_rows)
    latest = [row for row in period_rows if row.accepted_at == latest_acceptance]
    contexts = {(row.period_start, row.value) for row in latest}
    if len(contexts) != 1:
        return FactChoice(None, "conflicting_latest_context")
    return FactChoice(sorted(latest, key=lambda row: (row.accession, row.source_sha256))[-1], None)


@dataclass(frozen=True)
class FundamentalRatio:
    name: str
    value: float | None
    reason: str | None
    period_end: date | None
    available_at: datetime | None
    accessions: tuple[str, ...]
    source_hashes: tuple[str, ...]
    version: str = VERSION


def fundamental_ratios(
    facts: tuple[Fact, ...], *, cik: str, decision_at: datetime, stale_days: int = 550,
) -> tuple[FundamentalRatio, ...]:
    """Four predeclared ratios, with each numerator matched to same-period assets.

    Annual flows are actual reported annual contexts, never annualized quarters or
    summed YTD values. Assets must be positive. Negative earnings/cash flow survive.
    Missing gross profit for an issuer remains missing, not a universe exclusion.
    NetIncomeLoss retains its tagged parent-attributable meaning; this is not a
    claim of consolidated return on assets or earnings available to common shares.
    """
    definitions: tuple[tuple[str, str, Literal["instant", "annual"]], ...] = (
        ("liabilities_assets", "Liabilities", "instant"),
        ("annual_net_income_assets", "NetIncomeLoss", "annual"),
        ("annual_operating_cash_flow_assets",
         "NetCashProvidedByUsedInOperatingActivities", "annual"),
        ("annual_gross_profit_assets", "GrossProfit", "annual"),
    )
    output = []
    for name, concept, kind in definitions:
        numerator = choose_fact(facts, cik=cik, concept=concept, kind=kind,
                                decision_at=decision_at, stale_days=stale_days)
        if numerator.fact is None:
            output.append(FundamentalRatio(name, None, numerator.reason, None, None, (), ()))
            continue
        n = numerator.fact
        denominator = choose_fact(facts, cik=cik, concept="Assets", kind="instant",
                                  decision_at=decision_at, period_end=n.period_end,
                                  stale_days=stale_days)
        if denominator.fact is None:
            output.append(FundamentalRatio(name, None, "assets_" + str(denominator.reason),
                                            n.period_end, n.available_at, (n.accession,),
                                            (n.source_sha256,)))
            continue
        d = denominator.fact
        value = n.value / d.value if d.value > 0 else None
        reason = "nonpositive_assets" if value is None else None
        if value is not None and not math.isfinite(value):
            value, reason = None, "nonfinite_ratio"
        output.append(FundamentalRatio(
            name, value, reason, n.period_end, max(n.available_at, d.available_at),
            tuple(sorted({n.accession, d.accession})),
            tuple(sorted({n.source_sha256, d.source_sha256})),
        ))
    return tuple(output)
