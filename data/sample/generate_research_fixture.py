"""Generate the deterministic Phase 1 engineering-only price fixture."""

from __future__ import annotations

import csv
import math
from datetime import date, timedelta
from pathlib import Path


def sessions(count: int) -> list[date]:
    current = date(2023, 1, 3)
    holidays = {
        date(2023, 1, 16), date(2023, 2, 20), date(2023, 4, 7),
        date(2023, 5, 29), date(2023, 6, 19), date(2023, 7, 4),
        date(2023, 9, 4), date(2023, 11, 23), date(2023, 12, 25),
        date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19),
        date(2024, 3, 29), date(2024, 5, 27), date(2024, 6, 19),
        date(2024, 7, 4),
    }
    result: list[date] = []
    while len(result) < count:
        if current.weekday() < 5 and current not in holidays:
            result.append(current)
        current += timedelta(days=1)
    return result


def main() -> None:
    output = Path(__file__).with_name("research_daily_bars.csv")
    calendar_output = Path(__file__).with_name("us_sessions.csv")
    specifications = {
        "SPY": (380.0, 0.00035, 0.018, 95_000_000),
        "AAPL": (125.0, 0.00058, 0.025, 75_000_000),
        "MSFT": (225.0, 0.00066, 0.021, 45_000_000),
        "NVDA": (140.0, 0.00082, 0.040, 60_000_000),
        "AMZN": (92.0, 0.00048, 0.032, 80_000_000),
        "META": (132.0, 0.00055, 0.030, 42_000_000),
    }
    prior = {symbol: values[0] for symbol, values in specifications.items()}
    market_sessions = sessions(383)
    with calendar_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["exchange", "version", "date", "is_week_end"])
        for index, session in enumerate(market_sessions):
            next_week = (
                index == len(market_sessions) - 1
                or market_sessions[index + 1].isocalendar()[:2]
                != session.isocalendar()[:2]
            )
            writer.writerow(
                ["XNYS", "xnys-fixture-v1", session.isoformat(), str(next_week).lower()]
            )
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume"]
        )
        for index, session in enumerate(market_sessions[:380]):
            shock = -0.0028 if 220 <= index < 255 else 0.0
            for offset, (symbol, (_base, drift, amplitude, volume)) in enumerate(
                specifications.items()
            ):
                cycle = amplitude * math.sin(index / (12.0 + offset * 1.7) + offset)
                daily_return = drift + shock + cycle / 18.0
                opening = prior[symbol] * (1.0 + 0.002 * math.sin(index / 5.0 + offset))
                closing = prior[symbol] * (1.0 + daily_return)
                high = max(opening, closing) * 1.004
                low = min(opening, closing) * 0.996
                daily_volume = int(volume * (1.0 + 0.08 * math.sin(index / 9.0 + offset)))
                writer.writerow(
                    [
                        session.isoformat(),
                        symbol,
                        f"{opening:.6f}",
                        f"{high:.6f}",
                        f"{low:.6f}",
                        f"{closing:.6f}",
                        f"{closing:.6f}",
                        daily_volume,
                    ]
                )
                prior[symbol] = closing


if __name__ == "__main__":
    main()
