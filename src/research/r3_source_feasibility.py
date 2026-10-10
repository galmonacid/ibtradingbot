"""Point-in-time source audit for R3 Step 3; contains no model evaluation."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from src.config.r3_step3 import R3Step3Config

SEC_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}
SEC_CONCEPTS = {
    "Assets",
    "CommonStockSharesOutstanding",
    "GrossProfit",
    "Liabilities",
    "NetCashProvidedByUsedInOperatingActivities",
    "NetIncomeLoss",
    "OperatingIncomeLoss",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "StockholdersEquity",
}


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        )
        + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_new(path: Path, value: object) -> str:
    if path.exists():
        raise FileExistsError(f"immutable artifact already exists: {path}")
    payload = canonical_bytes(value)
    path.write_bytes(payload)
    return sha256_bytes(payload)


@dataclass(frozen=True)
class Filing:
    cik: str
    accession: str
    form: str
    accepted_at: datetime
    filing_date: date
    report_date: date | None
    primary_document: str
    source_sha256: str


@dataclass(frozen=True)
class Fact:
    cik: str
    accession: str
    form: str
    accepted_at: datetime
    available_at: datetime
    taxonomy: str
    concept: str
    unit: str
    value: float
    period_start: date | None
    period_end: date
    fiscal_year: int | None
    fiscal_period: str | None
    frame: str | None
    source_sha256: str
    transform_version: str = "r3-step3-sec-facts-v1"

    @property
    def duration_days(self) -> int | None:
        return None if self.period_start is None else (self.period_end - self.period_start).days

    @property
    def period_kind(self) -> Literal["instant", "quarterly", "year_to_date", "annual", "other"]:
        days = self.duration_days
        if days is None:
            return "instant"
        if 60 <= days <= 120:
            return "quarterly"
        if 330 <= days <= 400:
            return "annual"
        if 121 <= days <= 329:
            return "year_to_date"
        return "other"


def seeded_sample_order(config: R3Step3Config) -> tuple[str, ...]:
    values = [row.cik for row in config.sample]
    random.Random(config.sample_seed).shuffle(values)
    return tuple(values)


def parse_submissions(
    cik: str, payloads: tuple[tuple[dict[str, Any], str], ...]
) -> tuple[Filing, ...]:
    rows: list[Filing] = []
    for payload, source_sha in payloads:
        recent = payload.get("filings", {}).get("recent") if "filings" in payload else payload
        if not isinstance(recent, dict):
            continue
        accessions = recent.get("accessionNumber", [])
        for index, accession in enumerate(accessions):
            form = str(recent.get("form", [])[index])
            if form not in SEC_FORMS:
                continue
            acceptance = str(recent.get("acceptanceDateTime", [])[index])
            accepted = datetime.strptime(acceptance, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
            report = str(recent.get("reportDate", [])[index])
            rows.append(
                Filing(
                    cik,
                    str(accession),
                    form,
                    accepted,
                    date.fromisoformat(str(recent.get("filingDate", [])[index])),
                    date.fromisoformat(report) if report else None,
                    str(recent.get("primaryDocument", [])[index]),
                    source_sha,
                )
            )
    unique = {row.accession: row for row in rows}
    return tuple(sorted(unique.values(), key=lambda row: (row.accepted_at, row.accession)))


def parse_company_facts(
    cik: str,
    payload: dict[str, Any],
    source_sha256: str,
    filings: tuple[Filing, ...],
    latency_hours: int,
) -> tuple[Fact, ...]:
    accepted = {row.accession: row for row in filings}
    output: list[Fact] = []
    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        return ()
    for taxonomy, concepts in facts.items():
        if not isinstance(concepts, dict):
            continue
        for concept, detail in concepts.items():
            if concept not in SEC_CONCEPTS or not isinstance(detail, dict):
                continue
            units = detail.get("units", {})
            if not isinstance(units, dict):
                continue
            for unit, values in units.items():
                if not isinstance(values, list):
                    continue
                for raw in values:
                    if not isinstance(raw, dict) or str(raw.get("form")) not in SEC_FORMS:
                        continue
                    filing = accepted.get(str(raw.get("accn")))
                    value = raw.get("val")
                    if filing is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                    numeric = float(value)
                    if not math.isfinite(numeric):
                        continue
                    output.append(
                        Fact(
                            cik,
                            filing.accession,
                            filing.form,
                            filing.accepted_at,
                            filing.accepted_at + timedelta(hours=latency_hours),
                            str(taxonomy),
                            str(concept),
                            str(unit),
                            numeric,
                            date.fromisoformat(str(raw["start"])) if raw.get("start") else None,
                            date.fromisoformat(str(raw["end"])),
                            int(raw["fy"]) if isinstance(raw.get("fy"), int) else None,
                            str(raw["fp"]) if raw.get("fp") is not None else None,
                            str(raw["frame"]) if raw.get("frame") is not None else None,
                            source_sha256,
                        )
                    )
    return tuple(
        sorted(
            output,
            key=lambda row: (
                row.cik,
                row.concept,
                row.period_end,
                row.accepted_at,
                row.accession,
                row.unit,
            ),
        )
    )


def resolve_facts(facts: tuple[Fact, ...], decision_at: datetime) -> dict[str, object]:
    """Resolve only facts actually available at a decision timestamp."""
    eligible = [row for row in facts if row.available_at <= decision_at]
    grouped: defaultdict[tuple[str, date, str, date | None], list[Fact]] = defaultdict(list)
    for row in eligible:
        grouped[(row.concept, row.period_end, row.unit, row.period_start)].append(row)
    resolved: list[Fact] = []
    conflicts: list[dict[str, object]] = []
    for key, values in sorted(grouped.items(), key=lambda item: str(item[0])):
        latest_time = max(row.accepted_at for row in values)
        latest = [row for row in values if row.accepted_at == latest_time]
        distinct = {row.value for row in latest}
        if len(distinct) != 1:
            conflicts.append({"key": [str(value) for value in key], "values": sorted(distinct)})
            continue
        resolved.append(sorted(latest, key=lambda row: row.accession)[-1])
    return {
        "resolved": [asdict(row) for row in resolved],
        "conflicts": conflicts,
        "missing": not bool(resolved),
    }


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def build_audit_feature_row(
    facts: tuple[Fact, ...],
    *,
    decision_at: datetime,
    security_ids: tuple[str, ...],
) -> dict[str, object]:
    """Exercise availability -> identity -> formula without producing model input data."""
    if len(security_ids) != 1:
        return {
            "status": "ambiguous_security_join",
            "security_ids": list(security_ids),
            "gross_profit_assets": None,
        }
    resolved = resolve_facts(facts, decision_at)
    available = resolved["resolved"]
    assert isinstance(available, list)

    def latest(concept: str) -> float | None:
        matches = [row for row in available if row["concept"] == concept]
        if not matches:
            return None
        selected = max(matches, key=lambda row: (row["period_end"], row["accepted_at"]))
        return float(selected["value"])

    value = safe_ratio(latest("GrossProfit"), latest("Assets"))
    return {
        "status": "available" if value is not None else "missing_required_fact",
        "security_id": security_ids[0],
        "decision_at": decision_at,
        "gross_profit_assets": value,
        "feature_version": "r3-step3-integration-audit-v1",
    }


def full_protocol_folds_supported(first_feature_date: date | None) -> int:
    """All nine fixed folds require enriched features from 1999-01-29."""
    return 9 if first_feature_date is not None and first_feature_date <= date(1999, 1, 29) else 0


def feature_contract() -> list[dict[str, object]]:
    common = {
        "feature_version": "r3-step3-candidate-features-v1",
        "availability": "all inputs available by decision close; SEC inputs acceptance + 24h",
        "missing": "explicit null plus indicator; imputation median fitted on training only",
        "cross_section": "same-date contemporaneously eligible scoring universe only",
        "negative_zero": "negative numerators retained; zero denominators produce explicit null",
    }
    specs = [
        ("market_residual_momentum_63", "relative_momentum", "stock 63-session log return minus beta*market return", "adjusted closes", "63 sessions", "retained"),
        ("market_residual_momentum_126", "relative_momentum", "stock 126-session log return minus beta*market return", "adjusted closes", "126 sessions", "retained"),
        ("market_residual_momentum_252", "relative_momentum", "stock 252-session log return minus beta*market return", "adjusted closes", "252 sessions", "retained"),
        ("momentum_rank_63", "relative_momentum", "percentile rank of 63-session return", "adjusted closes", "63 sessions", "retained"),
        ("momentum_rank_126", "relative_momentum", "percentile rank of 126-session return", "adjusted closes", "126 sessions", "retained"),
        ("momentum_rank_252", "relative_momentum", "percentile rank of 252-session return", "adjusted closes", "252 sessions", "retained"),
        ("sector_relative_momentum_63", "relative_momentum", "stock return minus causal sector median return", "adjusted closes; dated sector", "63 sessions", "rejected_no_causal_sector_source"),
        ("sector_relative_momentum_126", "relative_momentum", "stock return minus causal sector median return", "adjusted closes; dated sector", "126 sessions", "rejected_no_causal_sector_source"),
        ("sector_relative_momentum_252", "relative_momentum", "stock return minus causal sector median return", "adjusted closes; dated sector", "252 sessions", "rejected_no_causal_sector_source"),
        ("downside_volatility_63", "risk_trading", "annualized stdev of negative daily returns, zeros otherwise", "adjusted closes", "63 sessions", "retained"),
        ("residual_volatility_63", "risk_trading", "annualized stdev of market-model residuals", "adjusted closes", "63 sessions", "retained"),
        ("beta_252", "risk_trading", "cov(stock,market)/var(market)", "adjusted closes", "252 sessions", "retained"),
        ("overnight_gap_frequency_63", "risk_trading", "count(abs(open/previous_close-1)>2%)/63", "raw opens/closes", "63 sessions", "retained"),
        ("volume_surprise_20", "risk_trading", "latest volume/median prior 20 volumes - 1", "raw volume", "21 sessions", "retained"),
        ("gross_profit_assets", "profitability_cash", "latest quarterly GrossProfit/latest Assets", "SEC USD facts", "latest quarter", "rejected_protocol_history"),
        ("operating_cash_flow_assets", "profitability_cash", "TTM operating cash flow/latest Assets", "SEC USD facts; quarterly/YTD derivation", "5 filings", "rejected_protocol_history"),
        ("accruals", "profitability_cash", "(TTM NetIncomeLoss-TTM operating cash flow)/latest Assets", "SEC USD facts", "5 filings", "rejected_protocol_history"),
        ("margin_change", "profitability_cash", "TTM OperatingIncomeLoss/TTM revenue minus prior-year ratio", "SEC USD facts", "9 filings", "rejected_protocol_history"),
        ("earnings_yield", "valuation_balance", "TTM NetIncomeLoss/decision-date market capitalization", "SEC facts; causal shares; raw close", "5 filings", "rejected_missing_causal_market_cap"),
        ("cash_flow_yield", "valuation_balance", "TTM operating cash flow/decision-date market capitalization", "SEC facts; causal shares; raw close", "5 filings", "rejected_missing_causal_market_cap"),
        ("leverage", "valuation_balance", "latest Liabilities/latest Assets", "SEC USD facts", "latest quarter", "rejected_protocol_history"),
        ("share_count_growth", "valuation_balance", "latest shares/prior-year shares - 1", "SEC shares facts", "5 filings", "rejected_identity_and_protocol_history"),
        ("sales_growth_yoy", "operating_change", "latest quarter revenue/same-quarter-prior-year revenue - 1", "SEC USD facts", "5 filings", "rejected_protocol_history"),
        ("profitability_change", "operating_change", "latest gross-profit/assets minus prior-year value", "SEC USD facts", "5 filings", "rejected_protocol_history"),
        ("days_since_filing", "operating_change", "decision timestamp minus latest usable SEC acceptance timestamp in days", "SEC acceptance timestamp", "1 filing", "rejected_protocol_history"),
        ("yield_curve_slope", "economic", "vintage 10y Treasury yield minus vintage 3m yield", "ALFRED vintages", "latest released observations", "rejected_api_key_not_supplied"),
        ("credit_spread_change_63", "economic", "63-session change in vintage BAA-minus-AAA spread", "ALFRED vintages", "63 sessions", "rejected_api_key_not_supplied"),
        ("inflation_vintage_yoy", "economic", "latest released CPI/latest released CPI 12 months earlier - 1", "ALFRED vintages", "13 releases", "rejected_api_key_not_supplied"),
    ]
    return [
        {
            **common,
            "name": name,
            "family": family,
            "formula": formula,
            "units": "ratio",
            "raw_fields": raw,
            "trailing_horizon": horizon,
            "filing_preference": "10-Q then 10-K; /A is new later information" if "SEC" in raw else None,
            "duplicate_rule": "same accession/context/unit differing values remain conflict" if "SEC" in raw else None,
            "stale_limit_days": 550 if "SEC" in raw else None,
            "status": status,
            "licence_permission": "SEC public read-only; local hashes only; redistribution not assessed as a dataset" if "SEC" in raw else "existing local source contract",
        }
        for name, family, formula, raw, horizon, status in specs
    ]


def audit_payloads(
    config: R3Step3Config,
    raw_directory: Path,
    access_manifest: list[dict[str, object]],
) -> dict[str, Any]:
    by_url = {str(row["url"]): row for row in access_manifest}
    all_facts: list[Fact] = []
    issuer_rows: list[dict[str, Any]] = []
    join_rows: list[dict[str, Any]] = []
    for sample in config.sample:
        main_url = f"https://data.sec.gov/submissions/CIK{sample.cik}.json"
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{sample.cik}.json"
        main_path = raw_directory / str(by_url[main_url]["file"])
        facts_path = raw_directory / str(by_url[facts_url]["file"])
        main = json.loads(main_path.read_text(encoding="utf-8"))
        payloads: list[tuple[dict[str, Any], str]] = [
            (main, str(by_url[main_url]["sha256"]))
        ]
        for old in main.get("filings", {}).get("files", []):
            url = f"https://data.sec.gov/submissions/{old['name']}"
            access = by_url.get(url)
            if access is not None:
                payloads.append(
                    (
                        json.loads(
                            (raw_directory / str(access["file"])).read_text(encoding="utf-8")
                        ),
                        str(access["sha256"]),
                    )
                )
        filings = parse_submissions(sample.cik, tuple(payloads))
        company_facts = json.loads(facts_path.read_text(encoding="utf-8"))
        facts = parse_company_facts(
            sample.cik,
            company_facts,
            str(by_url[facts_url]["sha256"]),
            filings,
            config.processing_latency_hours,
        )
        all_facts.extend(facts)
        issuer_rows.append(
            {
                "cik": sample.cik,
                "issuer": sample.issuer,
                "filings": len(filings),
                "amendments": sum(row.form.endswith("/A") for row in filings),
                "facts": len(facts),
                "first_accepted_at": min((row.accepted_at for row in filings), default=None),
                "last_accepted_at": max((row.accepted_at for row in filings), default=None),
                "after_hours_filings": sum(row.accepted_at.hour >= 16 for row in filings),
                "negative_facts": sum(row.value < 0 for row in facts),
                "period_kinds": dict(sorted(Counter(row.period_kind for row in facts).items())),
            }
        )
        join_rows.append(
            {
                "cik": sample.cik,
                "security_ids": list(sample.security_ids),
                "join_status": (
                    "ambiguous_multiple_security_ids"
                    if len(sample.security_ids) > 1
                    else "manually_matched_sample_only"
                ),
                "causal_effective_mapping_source": None,
                "qualification_usable": False,
            }
        )
    duplicates: defaultdict[tuple[object, ...], set[float]] = defaultdict(set)
    for fact in all_facts:
        duplicates[
            (
                fact.cik,
                fact.accession,
                fact.concept,
                fact.unit,
                fact.period_start,
                fact.period_end,
            )
        ].add(fact.value)
    conflicts = [
        {"key": [str(value) for value in key], "values": sorted(values)}
        for key, values in duplicates.items()
        if len(values) > 1
    ]
    usable_dates = [row.available_at.date() for row in all_facts]
    first = min(usable_dates) if usable_dates else None
    concept_counts = Counter(row.concept for row in all_facts)
    concept_ranges = {
        concept: {
            "first_available": min(
                row.available_at for row in all_facts if row.concept == concept
            ),
            "last_available": max(
                row.available_at for row in all_facts if row.concept == concept
            ),
            "issuer_count": len({row.cik for row in all_facts if row.concept == concept}),
        }
        for concept in sorted(concept_counts)
    }
    required = {
        "Assets",
        "NetCashProvidedByUsedInOperatingActivities",
        "NetIncomeLoss",
    }
    revenue = {
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    }
    annual_coverage: list[dict[str, object]] = []
    for year in range(1999, 2018):
        cutoff = datetime(year, 12, 31, 23, 59, tzinfo=UTC)
        stale_boundary = cutoff - timedelta(days=550)
        complete_ciks: set[str] = set()
        partial_ciks: set[str] = set()
        for sample in config.sample:
            available = {
                row.concept
                for row in all_facts
                if row.cik == sample.cik
                and stale_boundary <= row.available_at <= cutoff
            }
            if available:
                partial_ciks.add(sample.cik)
            if required <= available and bool(revenue & available):
                complete_ciks.add(sample.cik)
        annual_coverage.append(
            {
                "decision_year_end": year,
                "complete_case_issuers": len(complete_ciks),
                "partial_case_issuers": len(partial_ciks),
                "sample_issuers": len(config.sample),
                "complete_case_security_ids": sum(
                    len(sample.security_ids)
                    for sample in config.sample
                    if sample.cik in complete_ciks
                ),
            }
        )
    return {
        "issuers": issuer_rows,
        "joins": join_rows,
        "fact_summary": {
            "facts": len(all_facts),
            "first_causally_usable_date": first,
            "last_causally_usable_date": max(usable_dates) if usable_dates else None,
            "concept_coverage": dict(sorted(concept_counts.items())),
            "concept_ranges": concept_ranges,
            "duplicate_conflicts": len(conflicts),
            "total_audited_filings": sum(int(row["filings"]) for row in issuer_rows),
            "amendment_filings": sum(int(row["amendments"]) for row in issuer_rows),
            "amendment_frequency": (
                sum(int(row["amendments"]) for row in issuer_rows)
                / sum(int(row["filings"]) for row in issuer_rows)
            ),
            "after_hours_filings": sum(
                int(row["after_hours_filings"]) for row in issuer_rows
            ),
            "facts_shifted_across_utc_month_by_latency": sum(
                (row.accepted_at.year, row.accepted_at.month)
                != (row.available_at.year, row.available_at.month)
                for row in all_facts
            ),
            "missing_acceptance_rows_excluded": "company facts without a matched submissions acceptance timestamp are excluded",
            "processing_latency_hours": config.processing_latency_hours,
        },
        "conflicts": conflicts,
        "annual_coverage": annual_coverage,
        "facts": [asdict(row) for row in all_facts],
        "protocol": {
            "price_only_start": "1999-01-29",
            "sec_sample_start": first,
            "macro_vintage_start": None,
            "causal_sector_start": None,
            "required_full_folds": config.required_protocol_folds,
            "supported_full_folds": full_protocol_folds_supported(first),
            "decision": "stop",
            "blocker": "SEC features do not exist for the 1999 start of the frozen nine-fold protocol",
        },
    }
