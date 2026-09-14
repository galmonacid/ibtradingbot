from datetime import date

import pytest

from src.data.canonical_historical import CanonicalCorporateAction, CanonicalDailyBar
from src.data.fmp_reconciliation import (
    FmpDelistingObservation,
    FmpDividendObservation,
    FmpPriceObservation,
    FmpReconciliationError,
    FmpReconciliationReport,
    SupplementalQuarantine,
    reconcile_fmp_supplemental,
)

DAY = date(2020, 1, 2)
BAR = CanonicalDailyBar("SEC", "AAA", DAY, 10, 11, 9, 10.5, 10.5, 100, 10, 11, 9, 100)
ACTIONS = (
    CanonicalCorporateAction("SEC", "AAA", DAY, "dividend", 0.2),
    CanonicalCorporateAction("SEC", "AAA", DAY, "delisting", 0.0),
)


def test_matching_supplemental_observations_pass_without_mutating_canonical() -> None:
    report = reconcile_fmp_supplemental(
        canonical_bars=(BAR,),
        canonical_actions=ACTIONS,
        prices=(FmpPriceObservation("SEC", DAY, 10, 11, 9, 10.5, 100),),
        dividends=(FmpDividendObservation("SEC", DAY, 0.2),),
        delistings=(FmpDelistingObservation("SEC", DAY, "NYSE"),),
    )
    assert report.passed
    assert report.findings == ()


def test_disagreement_fails_unless_exact_interval_is_quarantined() -> None:
    arguments = dict(
        canonical_bars=(BAR,),
        canonical_actions=ACTIONS,
        prices=(FmpPriceObservation("SEC", DAY, 10, 11, 9, 10.6, 100),),
        dividends=(FmpDividendObservation("SEC", DAY, 0.2),),
        delistings=(FmpDelistingObservation("SEC", DAY, "NYSE"),),
    )
    assert not reconcile_fmp_supplemental(**arguments).passed
    report = reconcile_fmp_supplemental(
        **arguments,
        quarantines=(SupplementalQuarantine("price", "SEC", DAY, "provider mismatch"),),
    )
    assert report.passed
    assert report.findings[0].quarantined


def test_missing_extract_category_and_orphan_quarantine_fail_closed() -> None:
    with pytest.raises(FmpReconciliationError, match="price observations"):
        reconcile_fmp_supplemental(
            canonical_bars=(BAR,), canonical_actions=ACTIONS, prices=(), dividends=(), delistings=()
        )


def test_sparse_price_extract_cannot_cherry_pick_matching_rows() -> None:
    second = CanonicalDailyBar(
        "SEC", "AAA", date(2020, 1, 3), 11, 12, 10, 11.5, 11.5, 100, 11, 12, 10, 100
    )
    with pytest.raises(FmpReconciliationError, match="every canonical bar"):
        reconcile_fmp_supplemental(
            canonical_bars=(BAR, second),
            canonical_actions=ACTIONS,
            prices=(FmpPriceObservation("SEC", DAY, 10, 11, 9, 10.5, 100),),
            dividends=(FmpDividendObservation("SEC", DAY, 0.2),),
            delistings=(FmpDelistingObservation("SEC", DAY, "NYSE"),),
        )
    with pytest.raises(FmpReconciliationError, match="concrete reconciliation"):
        FmpReconciliationReport("a" * 64, "b" * 64, 1, 1, 1, (), True)
    with pytest.raises(FmpReconciliationError, match="does not correspond"):
        reconcile_fmp_supplemental(
            canonical_bars=(BAR,),
            canonical_actions=ACTIONS,
            prices=(FmpPriceObservation("SEC", DAY, 10, 11, 9, 10.5, 100),),
            dividends=(FmpDividendObservation("SEC", DAY, 0.2),),
            delistings=(FmpDelistingObservation("SEC", DAY, "NYSE"),),
            quarantines=(SupplementalQuarantine("price", "SEC", DAY, "not needed"),),
        )
