from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.data.source_adapters import (
    BoundAuditEvidenceSource,
    BoundIdentitySource,
    BoundMembershipSource,
    ParsedConstitutionEvents,
    SourceAdapterError,
    parse_index_constitution_events,
    parse_sp500_membership_snapshots,
)

EVENT_HEADER = "event_date,event_type,old_symbol,new_symbol,old_name,new_name,source_url,notes"


def test_parses_fja_membership_snapshots_strictly(tmp_path: Path) -> None:
    path = tmp_path / "membership.csv"
    path.write_text(
        'date,tickers\n2020-01-02,"AAA,BBB"\n2020-03-01,"BBB,CCC"\n',
        encoding="utf-8",
    )
    result = parse_sp500_membership_snapshots(path, minimum_members=2, maximum_members=3)

    assert result[0].as_of == date(2020, 1, 2)
    assert result[1].symbols == ("BBB", "CCC")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('Date,tickers\n2020-01-02,"AAA,BBB"\n', "unsupported membership schema"),
        ('date,tickers\n2020-01-02,"AAA,AAA"\n', "duplicate ticker"),
        ('date,tickers\n2020-02-01,"AAA,BBB"\n2020-01-01,"AAA,BBB"\n', "increasing"),
        ('date,tickers\n2020-01-02,"aaa,BBB"\n', "canonical US ticker"),
        ('date,tickers\n2020-01-02,"AAA"\n', "count outside"),
    ],
)
def test_membership_adapter_fails_closed(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "membership.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SourceAdapterError, match=message):
        parse_sp500_membership_snapshots(path, minimum_members=2, maximum_members=3)


def test_parses_events_into_changes_delistings_and_identity_intervals(tmp_path: Path) -> None:
    path = tmp_path / "us.csv"
    path.write_text(
        EVENT_HEADER
        + "\n2020-06-01,ticker_change,OLD,NEW,Old Corp,New Corp,https://example/a,rename"
        + "\n2022-01-03,name_change,HON,,Old Name,New Name,https://example/b,name only"
        + "\n2023-04-01,delisting,NEW,,New Corp,,https://example/c,ceased trading\n",
        encoding="utf-8",
    )
    result = parse_index_constitution_events(
        path, coverage_start=date(2010, 1, 1), known_symbols=("UNCHANGED",)
    )

    assert [(item.old_symbol, item.new_symbol) for item in result.ticker_changes] == [
        ("OLD", "NEW")
    ]
    assert result.delistings[0].symbol == "NEW"
    chain = [row for row in result.identity_intervals if row.symbol in {"OLD", "NEW"}]
    assert chain[0].security_id == chain[1].security_id
    assert any(row.symbol == "UNCHANGED" for row in result.identity_intervals)
    assert (chain[0].effective_to, chain[1].effective_from, chain[1].effective_to) == (
        date(2020, 6, 1),
        date(2020, 6, 1),
        date(2023, 4, 1),
    )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            "date,type,old,new\n2020-01-01,ticker_change,A,B",
            "unsupported index-constitution event schema",
        ),
        (
            EVENT_HEADER
            + "\n2021-01-01,ticker_change,A,B,A,B,https://example/a,n"
            + "\n2020-01-01,delisting,C,,C,,https://example/b,n\n",
            "non-decreasing",
        ),
        (
            EVENT_HEADER + "\n2020-01-01,ticker_change,A,,A,B,https://example/a,n\n",
            "ticker_change is incomplete",
        ),
        (
            EVENT_HEADER + "\n2020-01-01,merger,A,B,A,B,https://example/a,n\n",
            "unsupported event_type",
        ),
    ],
)
def test_event_adapter_rejects_unsupported_or_inconsistent_source(
    tmp_path: Path, rows: str, message: str
) -> None:
    path = tmp_path / "us.csv"
    path.write_text(rows, encoding="utf-8")
    with pytest.raises(SourceAdapterError, match=message):
        parse_index_constitution_events(path, coverage_start=date(2010, 1, 1))


def test_event_adapter_rejects_identity_graph_conflicts(tmp_path: Path) -> None:
    path = tmp_path / "us.csv"
    path.write_text(
        EVENT_HEADER
        + "\n2020-01-01,ticker_change,A,C,A,C,https://example/a,n"
        + "\n2020-01-02,ticker_change,B,C,B,C,https://example/b,n\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceAdapterError, match="multiple ticker predecessors"):
        parse_index_constitution_events(path, coverage_start=date(2010, 1, 1))

    path.write_text(
        EVENT_HEADER
        + "\n2020-01-01,ticker_change,A,B,A,B,https://example/a,n"
        + "\n2020-01-02,ticker_change,A,C,A,C,https://example/b,n\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceAdapterError, match="multiple successor events"):
        parse_index_constitution_events(path, coverage_start=date(2010, 1, 1))


def test_bound_source_results_cannot_be_caller_constructed() -> None:
    with pytest.raises(SourceAdapterError, match="source transformer"):
        BoundMembershipSource(object(), ())  # type: ignore[arg-type]
    with pytest.raises(SourceAdapterError, match="source transformer"):
        BoundIdentitySource(object(), ParsedConstitutionEvents((), (), (), ()))  # type: ignore[arg-type]
    with pytest.raises(SourceAdapterError, match="source transformer"):
        BoundAuditEvidenceSource(object(), ())  # type: ignore[arg-type]
