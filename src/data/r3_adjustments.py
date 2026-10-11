"""R3 ex-date-close total-return factor checks, separate from cash accounting.

Numerical consistency cannot certify a distribution's legal form, availability,
payment date, identity, or eligibility. Legacy certification is unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

from src.data.semantic_certification import CanonicalBar

CONVENTION = "r3-ex-date-close-total-return-v1"
CashBasis = Literal["pre_split_share", "post_split_share"]


def adjustment_context_keys(
    required: frozenset[tuple[str, date]],
    *,
    sessions: tuple[date, ...],
) -> frozenset[tuple[str, date]]:
    """Select current/predecessor lookup keys without expanding membership.

    Use the returned keys against the full identity-validated bar store, not a
    membership-filtered store. Missing bars remain missing. These keys must not
    be used as scoring eligibility or membership intervals.
    """
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ValueError("unique increasing exchange sessions required")
    positions = {day: index for index, day in enumerate(sessions)}
    context = set(required)
    for security_id, day in required:
        if not security_id or day not in positions:
            raise ValueError("nonempty identity and calendar session required")
        index = positions[day]
        if index == 0:
            raise ValueError("calendar lacks the required predecessor session")
        context.add((security_id, sessions[index - 1]))
    return frozenset(context)


@dataclass(frozen=True)
class AdjustmentEvent:
    security_id: str
    session: date
    split_ratio: float = 1.0  # New shares per old share.
    distribution_amount: float = 0.0
    cash_basis: CashBasis | None = None


@dataclass(frozen=True)
class FactorCheck:
    observed: float
    expected: float
    consistent: bool
    convention: str = CONVENTION


def check_adjustment_pair(
    previous: CanonicalBar,
    current: CanonicalBar,
    event: AdjustmentEvent,
    *,
    previous_session: date,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> FactorCheck:
    """Check adjacent bars using a caller-verified exchange-calendar predecessor.

    For one old share, ending value is split_ratio * current_price plus a
    distribution in old-share units. Divide by current_price to obtain the
    expected change in adjusted/raw factors. Combined split/distribution events
    require explicit amount units; provider units must never be guessed.

    The amount can be a provider's cash-equivalent field. A successful check
    grants no permission to credit cash, reinvest, or admit the security.
    """
    if not event.security_id or not (
        previous.security_id == current.security_id == event.security_id
    ):
        raise ValueError("one nonempty security identity required")
    if previous.session != previous_session or current.session <= previous_session:
        raise ValueError("adjacent exchange-session bars required")
    if event.session != current.session:
        raise ValueError("event must belong to the current session")
    prices = (
        previous.raw_close, previous.adjusted_close,
        current.raw_close, current.adjusted_close, event.split_ratio,
    )
    if any(not math.isfinite(x) or x <= 0 for x in prices):
        raise ValueError("prices and split ratio must be finite and positive")
    if not math.isfinite(event.distribution_amount) or event.distribution_amount < 0:
        raise ValueError("distribution must be finite and nonnegative")
    if any(
        not math.isfinite(x) or x < 0
        for x in (relative_tolerance, absolute_tolerance)
    ):
        raise ValueError("tolerances must be finite and nonnegative")
    if event.cash_basis not in (None, "pre_split_share", "post_split_share"):
        raise ValueError("unsupported distribution units")
    if event.split_ratio != 1 and event.distribution_amount and event.cash_basis is None:
        raise ValueError("combined split/distribution requires explicit share units")
    amount = event.distribution_amount
    if event.cash_basis == "post_split_share":
        amount *= event.split_ratio
    prior_factor = previous.adjusted_close / previous.raw_close
    if not math.isfinite(prior_factor) or prior_factor <= 0:
        raise ValueError("nonfinite or nonpositive derived factor")
    observed = (current.adjusted_close / current.raw_close) / prior_factor
    expected = event.split_ratio + amount / current.raw_close
    if not math.isfinite(observed) or not math.isfinite(expected) or observed <= 0:
        raise ValueError("nonfinite or nonpositive derived factor")
    return FactorCheck(
        observed, expected,
        math.isclose(observed, expected, rel_tol=relative_tolerance, abs_tol=absolute_tolerance),
    )
