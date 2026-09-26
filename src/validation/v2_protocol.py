"""Fixed V2 fragility design and fail-closed, continuous fresh-test boundary.

These guards establish protocol eligibility only; all existing deployment gates,
bootstrap and currency/account feasibility checks remain independently mandatory.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.data.calendar import TradingCalendar


@dataclass(frozen=True)
class SensitivityVariant:
    axis: str
    value: int | float | str

    @property
    def name(self) -> str:
        return f"{self.axis}={self.value}"


FIXED_SENSITIVITIES = tuple(
    SensitivityVariant(axis, value)
    for axis, values in (
        ("target_positions", (3, 5)),
        ("numerator_offset", (10, 42)),
        ("selection_schedule", ("penultimate_monthly", "biweekly")),
        ("stock_sma", (160, 240)),
        ("spy_sma", (160, 240)),
        ("volatility_ceiling", (0.10, 0.14)),
        ("long_covariance_window", (42, 84)),
        ("discretionary_band", (0.0, 0.05)),
    )
    for value in values
)


@dataclass(frozen=True)
class SensitivityMetrics:
    net_cagr: float
    sharpe: float
    maximum_drawdown: float
    executable: bool = True


@dataclass(frozen=True)
class RobustnessResult:
    passed: bool
    viable_variants: tuple[str, ...]
    failed_axes: tuple[str, ...]


def assess_v2_robustness(results: Mapping[str, SensitivityMetrics]) -> RobustnessResult:
    """Require 13/16 fixed OAT neighbors and at least one on each axis.

    Missing/unexecutable/non-finite variants fail; extra variants cannot rescue them.
    """
    viable = []
    axes = set()
    for variant in FIXED_SENSITIVITIES:
        metric = results.get(variant.name)
        if (
            metric is not None
            and metric.executable
            and all(
                math.isfinite(value)
                for value in (metric.net_cagr, metric.sharpe, metric.maximum_drawdown)
            )
            and metric.net_cagr >= 0.06
            and metric.sharpe >= 0.6
            and (0 <= metric.maximum_drawdown <= 0.15)
        ):
            viable.append(variant.name)
            axes.add(variant.axis)
    failed = tuple(sorted({item.axis for item in FIXED_SENSITIVITIES} - axes))
    return RobustnessResult(len(viable) >= 13 and not failed, tuple(viable), failed)


@dataclass(frozen=True)
class PositionFill:
    """Signed actual fill quantity; ticker is diagnostic, identity is stable.

    Quantities must use a consistent share basis across corporate actions. Supply
    actual split-adjusted inventory deltas before subsequent fills when applicable.
    """

    security_id: str
    session: date
    quantity_delta: Decimal
    ticker: str = ""


@dataclass(frozen=True)
class PositionEpisode:
    security_id: str
    entry: date
    exit: date


def completed_position_episodes(
    fills: tuple[PositionFill, ...], *, start: date, end: date
) -> tuple[PositionEpisode, ...]:
    """Count zero-to-zero actual holdings, never partial exits or ticker aliases.

    Supply full inception history, including pre-test fills, so carried positions
    cannot be relabelled as independent fresh episodes. Same-session order is causal.
    """
    if start > end:
        raise ValueError("episode period must be increasing")
    balances: dict[str, Decimal] = {}
    entries: dict[str, date] = {}
    episodes = []
    previous: date | None = None
    for fill in fills:
        if previous is not None and fill.session < previous:
            raise ValueError("fills must be chronological")
        previous = fill.session
        if not fill.security_id.strip() or not fill.quantity_delta.is_finite():
            raise ValueError("fills need a stable identity and finite quantity")
        if fill.quantity_delta == 0:
            raise ValueError("zero fills are not inventory events")
        old = balances.get(fill.security_id, Decimal(0))
        new = old + fill.quantity_delta
        if new < 0:
            raise ValueError("fill history cannot produce a short position")
        if old == 0:
            entries[fill.security_id] = fill.session
        if new == 0:
            entry = entries.pop(fill.security_id)
            if start <= entry <= fill.session <= end:
                episodes.append(PositionEpisode(fill.security_id, entry, fill.session))
        balances[fill.security_id] = new
    return tuple(episodes)


BOUND_IDENTITIES = (
    "strategy_spec",
    "source_tree",
    "config",
    "costs",
    "universe_policy",
    "currencies",
    "calendar",
    "benchmark_rules",
    "data_evidence",
)
ENDPOINT_RULE = "first_calendar_year_end_with_756_sessions_150_lots_150_episodes"


@dataclass(frozen=True)
class V2FreezeManifest:
    """Immutable protocol identities; changed code/inputs require a new freeze.

    Calendar identity is the pinned TradingCalendar source SHA-256. All other
    identities are canonical SHA-256 digests supplied by the research runner.
    """

    frozen_at: datetime
    source_revision: str
    identities: tuple[tuple[str, str], ...]
    data_cutoff: date
    biweekly_anchor: date
    strategy_version: str = "monthly-momentum-v2"
    sensitivities: tuple[SensitivityVariant, ...] = FIXED_SENSITIVITIES
    endpoint_rule: str = ENDPOINT_RULE

    def __post_init__(self) -> None:
        if self.frozen_at.utcoffset() is None:
            raise ValueError("freeze timestamp must be timezone aware")
        if self.strategy_version != "monthly-momentum-v2":
            raise ValueError("freeze must name the V2 candidate")
        if len(self.source_revision) != 40 or any(
            char not in "0123456789abcdef" for char in self.source_revision
        ):
            raise ValueError("freeze needs a canonical source revision")
        identities = dict(self.identities)
        if len(identities) != len(self.identities) or set(identities) != set(BOUND_IDENTITIES):
            raise ValueError("freeze must bind every required identity exactly once")
        if any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in identities.values()
        ):
            raise ValueError("freeze identities must be canonical SHA-256")
        if self.data_cutoff > self.frozen_at.astimezone(ZoneInfo("America/New_York")).date():
            raise ValueError("data cutoff cannot follow freeze")
        if self.sensitivities != FIXED_SENSITIVITIES or self.endpoint_rule != ENDPOINT_RULE:
            raise ValueError("V2 sensitivity and endpoint protocol cannot be changed")

    @property
    def sha256(self) -> str:
        payload = {
            "frozen_at": self.frozen_at.isoformat(),
            "revision": self.source_revision,
            "identities": sorted(self.identities),
            "data_cutoff": self.data_cutoff.isoformat(),
            "anchor": self.biweekly_anchor.isoformat(),
            "strategy": self.strategy_version,
            "sensitivities": [item.name for item in self.sensitivities],
            "endpoint": self.endpoint_rule,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class FreshWindowResult:
    eligible: bool
    reason: str
    endpoint: date | None = None


def validate_fresh_window(
    *,
    development: bool,
    freeze: V2FreezeManifest | None,
    actual_identities: Mapping[str, str],
    actual_source_revision: str,
    calendar: TradingCalendar,
    observed_sessions: tuple[date, ...],
    closed_lot_dates: tuple[date, ...],
    episodes: tuple[PositionEpisode, ...],
) -> FreshWindowResult:
    """Enforce continuous future evidence and the first predeclared endpoint.

    Lot dates must represent independently verified FIFO closures whose entries
    also lie in this test; episodes should come from completed_position_episodes.
    This function does not certify financial performance or the submitted ledger.
    """
    if development:
        return FreshWindowResult(False, "development evidence cannot qualify")
    if freeze is None:
        return FreshWindowResult(False, "freeze manifest required")
    if dict(freeze.identities) != dict(actual_identities) or (
        actual_source_revision != freeze.source_revision
    ):
        return FreshWindowResult(False, "frozen identities differ from actual run")
    if calendar.exchange != "XNYS" or calendar.source_sha256 != actual_identities["calendar"]:
        return FreshWindowResult(False, "pinned XNYS calendar required")
    sessions = calendar.sessions
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        return FreshWindowResult(False, "calendar must be sorted and unique")
    frozen_day = freeze.frozen_at.astimezone(ZoneInfo("America/New_York")).date()
    # Exclude freeze-day intraday data: the test starts in the following session.
    future = tuple(day for day in sessions if day > frozen_day)
    completed_weeks = {
        left
        for left, right in zip(sessions, sessions[1:], strict=False)
        if left.isocalendar()[:2] != right.isocalendar()[:2]
    }
    if sessions[0] > frozen_day or not future or freeze.biweekly_anchor not in completed_weeks:
        return FreshWindowResult(False, "calendar does not cover freeze and anchored schedule")
    if not observed_sessions or observed_sessions != future[: len(observed_sessions)]:
        return FreshWindowResult(False, "test must begin after freeze and contain every session")
    start, end = observed_sessions[0], observed_sessions[-1]
    if any(not start <= day <= end or day not in observed_sessions for day in closed_lot_dates):
        return FreshWindowResult(False, "lot closure outside observed test")
    if any(
        not start <= item.entry <= item.exit <= end
        or item.entry not in observed_sessions
        or item.exit not in observed_sessions
        for item in episodes
    ):
        return FreshWindowResult(False, "episode not fully inside observed test")
    ordered_episodes = sorted(episodes, key=lambda item: (item.security_id, item.entry, item.exit))
    previous_episode: PositionEpisode | None = None
    for episode in ordered_episodes:
        if previous_episode is not None and episode.security_id == previous_episode.security_id:
            if episode == previous_episode or episode.entry < previous_episode.exit:
                return FreshWindowResult(False, "duplicate or overlapping independent episodes")
        previous_episode = episode
    # The next calendar session proves that the last December row is truly year-end.
    year_ends = {
        left for left, right in zip(sessions, sessions[1:], strict=False) if left.year < right.year
    }
    for index, day in enumerate(observed_sessions, start=1):
        if (
            day in year_ends
            and index >= 756
            and (
                sum(closed <= day for closed in closed_lot_dates) >= 150
                and sum(item.exit <= day for item in episodes) >= 150
            )
        ):
            if end != day:
                return FreshWindowResult(False, "test extended beyond first eligible endpoint", day)
            return FreshWindowResult(
                True, "fresh protocol boundary satisfied; gates still required", day
            )
    return FreshWindowResult(False, "minimum evidence or first eligible year-end not reached")
