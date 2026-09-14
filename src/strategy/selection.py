"""Stateful portfolio selection with a deterministic rank buffer."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.strategy.ranking import RankedStock


@dataclass(frozen=True)
class SelectionExclusion:
    """A previously held symbol that the selector did not retain."""

    symbol: str
    reason: str


@dataclass(frozen=True)
class SelectionResult:
    """Ordered target holdings and incumbent-removal reasons."""

    selected: tuple[RankedStock, ...]
    exclusions: tuple[SelectionExclusion, ...]


def select_with_rank_hysteresis(
    ranked: Iterable[RankedStock],
    incumbents: Iterable[str],
    target_positions: int,
    *,
    mandatory_exclusions: Mapping[str, str] | None = None,
) -> SelectionResult:
    """Retain incumbents through ``2N`` and fill vacancies from the top ``N``.

    Mandatory exclusions (for example, trend or data ineligibility) take priority
    over the rank buffer. Retained incumbents take priority over new entrants, so a
    small rank change does not cause replacement turnover. Results are returned in
    current rank order, with symbol as a deterministic secondary key.
    """

    if type(target_positions) is not int or target_positions < 1:
        raise ValueError("target_positions must be a positive integer")

    ordered = sorted(tuple(ranked), key=lambda item: (item.rank, item.symbol))
    seen_symbols: set[str] = set()
    seen_ranks: set[int] = set()
    for item in ordered:
        if not item.symbol:
            raise ValueError("ranked symbols must be non-empty")
        if item.symbol in seen_symbols:
            raise ValueError(f"duplicate ranked symbol: {item.symbol}")
        if isinstance(item.rank, bool) or item.rank < 1:
            raise ValueError("ranks must be positive integers")
        if item.rank in seen_ranks:
            raise ValueError(f"duplicate rank: {item.rank}")
        if not math.isfinite(item.score):
            raise ValueError(f"score must be finite for {item.symbol}")
        seen_symbols.add(item.symbol)
        seen_ranks.add(item.rank)

    prior = tuple(dict.fromkeys(incumbents))
    if any(not symbol for symbol in prior):
        raise ValueError("incumbent symbols must be non-empty")
    if len(prior) > target_positions:
        raise ValueError("incumbents cannot exceed target_positions")
    forced_out = dict(mandatory_exclusions or {})
    by_symbol = {item.symbol: item for item in ordered}
    retained: list[RankedStock] = []
    exclusions: list[SelectionExclusion] = []

    for symbol in prior:
        if symbol in forced_out:
            exclusions.append(SelectionExclusion(symbol, forced_out[symbol]))
            continue
        incumbent_rank = by_symbol.get(symbol)
        if incumbent_rank is None:
            exclusions.append(SelectionExclusion(symbol, "not_ranked"))
        elif incumbent_rank.rank <= 2 * target_positions:
            retained.append(incumbent_rank)
        else:
            exclusions.append(SelectionExclusion(symbol, "rank_below_exit_buffer"))

    chosen = {item.symbol: item for item in retained[:target_positions]}
    if len(chosen) < target_positions:
        for item in ordered:
            if len(chosen) == target_positions:
                break
            if item.rank > target_positions:
                break
            if item.symbol not in chosen and item.symbol not in forced_out:
                chosen[item.symbol] = item

    selected = tuple(sorted(chosen.values(), key=lambda item: (item.rank, item.symbol)))
    return SelectionResult(selected, tuple(exclusions))
