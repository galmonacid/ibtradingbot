from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from src.features.r3_fundamentals import choose_fact, fundamental_ratios
from src.research.r3_source_feasibility import Fact

AT = datetime.fromisoformat("2020-03-01T16:00:00+00:00")
END = date(2019, 12, 31)


def fact(concept: str, value: float, *, annual: bool = False) -> Fact:
    return Fact("0000000001", "a", "10-K", AT - timedelta(days=2), AT - timedelta(days=1),
                "us-gaap", concept, "USD", value,
                date(2019, 1, 1) if annual else None, END, 2019, "FY", None, "a" * 64)


def ratio(rows: tuple[Fact, ...], name: str = "annual_net_income_assets"):
    return next(row for row in fundamental_ratios(rows, cik="0000000001", decision_at=AT)
                if row.name == name)


def test_annual_ratio_and_negative_income_retained() -> None:
    result = ratio((fact("Assets", 100), fact("NetIncomeLoss", -20, annual=True)))
    assert result.value == -0.2
    assert result.period_end == END
    assert result.available_at == AT - timedelta(days=1)
    assert result.source_hashes == ("a" * 64,)


def test_future_filing_mutations_do_not_change_earlier_result() -> None:
    rows = (fact("Assets", 100), fact("NetIncomeLoss", 20, annual=True))
    future = replace(rows[1], value=999, accepted_at=AT + timedelta(days=1),
                     available_at=AT + timedelta(days=2), accession="amendment")
    assert ratio(rows + (future,)) == ratio(rows)
    future_changed = replace(future, value=-999)
    assert ratio(rows + (future_changed,)) == ratio(rows)


def test_amendment_only_applies_after_processing_latency() -> None:
    rows = (fact("Assets", 100), fact("NetIncomeLoss", 20, annual=True))
    amendment = replace(rows[1], accepted_at=AT - timedelta(hours=12),
                        available_at=AT + timedelta(hours=12), value=30)
    assert ratio(rows + (amendment,)).value == 0.2
    after = fundamental_ratios(rows + (amendment,), cik="0000000001",
                               decision_at=AT + timedelta(days=1))
    assert next(row for row in after if row.name == "annual_net_income_assets").value == 0.3


def test_matching_fiscal_end_required_not_latest_balance_sheet() -> None:
    rows = (replace(fact("Assets", 100), period_end=date(2019, 9, 30)),
            fact("NetIncomeLoss", 20, annual=True))
    assert ratio(rows).value is None
    assert ratio(rows).reason == "assets_missing_available_usd_context"


@pytest.mark.parametrize("start", [date(2019, 10, 1), date(2019, 4, 1)])
def test_quarter_and_ytd_never_substitute_for_annual(start: date) -> None:
    rows = (fact("Assets", 100), replace(fact("NetIncomeLoss", 20, annual=True),
                                        period_start=start))
    assert ratio(rows).value is None


@pytest.mark.parametrize("value", [0, -100])
def test_nonpositive_assets_rejected(value: float) -> None:
    assert ratio((fact("Assets", value), fact("NetIncomeLoss", 20, annual=True))).reason == (
        "nonpositive_assets"
    )


def test_conflicting_latest_context_does_not_fall_back() -> None:
    a = fact("NetIncomeLoss", 20, annual=True)
    conflicting = replace(a, value=30)
    assert ratio((fact("Assets", 100), a, conflicting)).reason == "conflicting_latest_context"


def test_currency_and_taxonomy_not_blended() -> None:
    n = replace(fact("NetIncomeLoss", 20, annual=True), unit="CAD")
    assert ratio((fact("Assets", 100), n)).value is None
    n = replace(n, unit="USD", taxonomy="custom")
    assert ratio((fact("Assets", 100), n)).value is None


def test_stale_period_boundary() -> None:
    a = fact("Assets", 100)
    at = a.available_at + timedelta(days=365)
    days = (at.date() - END).days
    assert choose_fact((a,), cik=a.cik, concept="Assets", kind="instant", decision_at=at,
                       stale_days=days).fact == a
    assert choose_fact((a,), cik=a.cik, concept="Assets", kind="instant", decision_at=at,
                       stale_days=days - 1).reason == "stale_fiscal_period"


def test_cross_issuer_and_bad_availability_fail() -> None:
    a = fact("Assets", 100)
    with pytest.raises(ValueError, match="one declared issuer"):
        ratio((replace(a, cik="0000000002"),))
    with pytest.raises(ValueError, match="precedes"):
        ratio((replace(a, available_at=a.accepted_at - timedelta(days=1)),))
    with pytest.raises(ValueError, match="aware decision"):
        fundamental_ratios((a,), cik=a.cik, decision_at=AT.replace(tzinfo=None))
