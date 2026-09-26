"""Deterministic normalization of attributed ECB reference-rate archives.

This module does not fetch data. Publication availability is deliberately modeled
at the following UTC midnight; the source archive is not a historical vintage store.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.data.fx import FXHistory, load_fx_history

ECB_SOURCE = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
ECB_LICENCE = "https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html"


def normalize_ecb_archive(
    archive: Path,
    destination: Path,
    *,
    start: date,
    end: date,
    retrieved_at: datetime,
) -> FXHistory:
    """Preserve archive provenance and disclose the cross-rate/publication assumptions."""
    if start > end or retrieved_at.utcoffset() is None:
        raise ValueError("ordered date interval and timezone-aware retrieval required")
    raw = archive.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        csv_names = [name for name in bundle.namelist() if name.endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError("ECB archive must contain exactly one CSV")
        reader = csv.DictReader(io.StringIO(bundle.read(csv_names[0]).decode("utf-8-sig")))
        if reader.fieldnames is None:
            raise ValueError("ECB CSV is empty")
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        if not {"Date", "GBP", "USD"}.issubset(reader.fieldnames):
            raise ValueError("ECB archive lacks Date/GBP/USD columns")
        observations: dict[date, tuple[datetime, datetime, float]] = {}
        for row in reader:
            day = date.fromisoformat(row["Date"].strip())
            if not start <= day <= end:
                continue
            if day in observations:
                raise ValueError("duplicate ECB observation date")
            gbp, usd = float(row["GBP"]), float(row["USD"])
            if not all(math.isfinite(value) and value > 0 for value in (gbp, usd)):
                raise ValueError("invalid ECB reference rate")
            observed = datetime.combine(day, time(14, 10), ZoneInfo("Europe/Berlin"))
            available = datetime.combine(day + timedelta(days=1), time(), UTC)
            if available > retrieved_at:
                raise ValueError("modeled availability follows retrieval")
            observations[day] = (observed, available, gbp / usd)
    if not observations:
        raise ValueError("no ECB observations in requested interval")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("observed_at", "available_at", "gbp_per_usd"))
    for day in sorted(observations):
        observed, available, rate = observations[day]
        writer.writerow((observed.isoformat(), available.isoformat(), format(rate, ".17g")))
    normalized = buffer.getvalue().encode()
    manifest = {
        "source": "European Central Bank: " + ECB_SOURCE,
        "licence": ECB_LICENCE + " (free use with attribution; modifications disclosed)",
        "retrieved_at": retrieved_at.isoformat(),
        "sha256": hashlib.sha256(normalized).hexdigest(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "quote": "GBP per USD",
        "synthetic": False,
        "vintage_certified": False,
        "usage": "development_only_retrospective_reference_archive",
        "transformation": "GBP per EUR divided by USD per EUR",
        "availability_assumption": "following calendar day at 00:00 UTC; not vintage-certified",
        "observed_time_assumption": "14:10 Europe/Berlin on ECB observation date",
        "start": min(observations).isoformat(),
        "end": max(observations).isoformat(),
        "rows": len(observations),
    }
    destination.mkdir(parents=True, exist_ok=True)
    csv_path, manifest_path = destination / "fx.csv", destination / "fx_manifest.json"
    csv_path.write_bytes(normalized)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return load_fx_history(csv_path, manifest_path)
