"""Timestamped, provenance-bearing GBP per USD observations for offline research."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class FXObservation:
    observed_at: datetime
    available_at: datetime
    gbp_per_usd: float

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("FX timestamps must include timezone")
        if self.available_at < self.observed_at:
            raise ValueError("FX cannot be available before observation")
        if not math.isfinite(self.gbp_per_usd) or self.gbp_per_usd <= 0:
            raise ValueError("GBP per USD must be finite and positive")


@dataclass(frozen=True)
class FXHistory:
    observations: tuple[FXObservation, ...]
    source: str
    licence: str
    sha256: str
    synthetic: bool = False

    def __post_init__(self) -> None:
        if not self.observations or not self.source.strip() or not self.licence.strip():
            raise ValueError("FX observations, source and licence are required")
        keys = tuple(row.available_at for row in self.observations)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("FX availability timestamps must be unique and increasing")

    def at(self, timestamp: datetime, *, max_age_days: int = 4) -> FXObservation:
        """Use only observations already available; never a same-day future fixing."""
        if timestamp.tzinfo is None or max_age_days < 0:
            raise ValueError("aware timestamp and non-negative FX age required")
        index = bisect_right(tuple(row.available_at for row in self.observations), timestamp) - 1
        if index < 0:
            raise ValueError("no causally available FX observation")
        row = self.observations[index]
        if timestamp - row.observed_at > timedelta(days=max_age_days):
            raise ValueError("FX observation is stale")
        return row


def load_fx_history(csv_path: Path, manifest_path: Path) -> FXHistory:
    """Read immutable normalized observations, bound to source/licence/retrieval metadata."""
    raw = csv_path.read_bytes()
    manifest = json.loads(manifest_path.read_text())
    digest = hashlib.sha256(raw).hexdigest()
    if manifest.get("sha256") != digest or manifest.get("quote") != "GBP per USD":
        raise ValueError("FX manifest hash or quote convention mismatch")
    retrieved = datetime.fromisoformat(manifest["retrieved_at"])
    if retrieved.tzinfo is None:
        raise ValueError("FX retrieval timestamp must include timezone")
    reader = csv.DictReader(raw.decode().splitlines())
    if reader.fieldnames != ["observed_at", "available_at", "gbp_per_usd"]:
        raise ValueError("FX CSV requires observed_at,available_at,gbp_per_usd")
    observations = tuple(
        FXObservation(
            datetime.fromisoformat(row["observed_at"]),
            datetime.fromisoformat(row["available_at"]),
            float(row["gbp_per_usd"]),
        )
        for row in reader
    )
    if any(row.available_at > retrieved for row in observations):
        raise ValueError("FX observations cannot postdate retrieval")
    synthetic = manifest.get("synthetic", False)
    if not isinstance(synthetic, bool):
        raise ValueError("FX synthetic flag must be boolean")
    return FXHistory(
        observations,
        manifest["source"],
        manifest["licence"],
        hashlib.sha256(raw + manifest_path.read_bytes()).hexdigest(),
        synthetic,
    )
