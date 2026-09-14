from __future__ import annotations

import pytest

from src.strategy import RankedStock, select_with_rank_hysteresis


def _ranked(*symbols: str) -> tuple[RankedStock, ...]:
    return tuple(
        RankedStock(symbol=symbol, rank=rank, score=float(len(symbols) - rank))
        for rank, symbol in enumerate(symbols, start=1)
    )


def test_retains_incumbents_inside_exit_buffer_before_adding_entrants() -> None:
    ranking = _ranked("NEW1", "NEW2", "HELD1", "HELD2")

    result = select_with_rank_hysteresis(
        reversed(ranking), incumbents=("HELD2", "HELD1"), target_positions=2
    )

    assert [item.symbol for item in result.selected] == ["HELD1", "HELD2"]
    assert result.exclusions == ()


def test_exits_beyond_buffer_and_fills_only_from_entry_rank() -> None:
    ranking = _ranked("NEW", "OTHER", "THIRD", "FOURTH", "STALE")

    result = select_with_rank_hysteresis(ranking, incumbents=("STALE", "THIRD"), target_positions=2)

    assert [item.symbol for item in result.selected] == ["NEW", "THIRD"]
    assert [(item.symbol, item.reason) for item in result.exclusions] == [
        ("STALE", "rank_below_exit_buffer")
    ]


def test_mandatory_ineligibility_overrides_rank_buffer() -> None:
    ranking = _ranked("HELD", "NEW", "LOW")

    result = select_with_rank_hysteresis(
        ranking,
        incumbents=("HELD",),
        target_positions=2,
        mandatory_exclusions={"HELD": "price_not_above_sma200"},
    )

    assert [item.symbol for item in result.selected] == ["NEW"]
    assert [(item.symbol, item.reason) for item in result.exclusions] == [
        ("HELD", "price_not_above_sma200")
    ]


def test_absent_incumbent_is_removed_and_rank_below_n_cannot_enter() -> None:
    result = select_with_rank_hysteresis(
        (RankedStock("THIRD", 3, 1.0),),
        incumbents=("MISSING",),
        target_positions=2,
    )

    assert result.selected == ()
    assert [(item.symbol, item.reason) for item in result.exclusions] == [("MISSING", "not_ranked")]


@pytest.mark.parametrize("target", [0, -1, True, 2.5])
def test_rejects_invalid_target_position_count(target: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        select_with_rank_hysteresis((), (), target)  # type: ignore[arg-type]


def test_rejects_ambiguous_ranking_inputs() -> None:
    with pytest.raises(ValueError, match="duplicate ranked symbol"):
        select_with_rank_hysteresis((RankedStock("AAA", 1, 1.0), RankedStock("AAA", 2, 0.0)), (), 2)
    with pytest.raises(ValueError, match="duplicate rank"):
        select_with_rank_hysteresis((RankedStock("AAA", 1, 1.0), RankedStock("BBB", 1, 0.0)), (), 2)


def test_rank_buffer_turnover_is_no_greater_than_unbuffered_selection() -> None:
    first = select_with_rank_hysteresis(_ranked("AAA", "BBB", "CCC", "DDD"), (), 2)
    second_ranking = _ranked("CCC", "DDD", "AAA", "BBB")
    buffered = select_with_rank_hysteresis(
        second_ranking,
        (item.symbol for item in first.selected),
        2,
    )
    first_symbols = {item.symbol for item in first.selected}
    buffered_symbols = {item.symbol for item in buffered.selected}
    unbuffered_symbols = {item.symbol for item in second_ranking[:2]}

    buffered_turnover_sides = len(first_symbols ^ buffered_symbols)
    unbuffered_turnover_sides = len(first_symbols ^ unbuffered_symbols)
    assert buffered_turnover_sides == 0
    assert buffered_turnover_sides <= unbuffered_turnover_sides
