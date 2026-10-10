"""Extract source-bound SEC cover observations; never infer security-master intervals.

A cover's fiscal context period is not its publication time or the start of a
symbol interval. These observations support manual identity remediation only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser

FIELDS = ("dei:security12btitle", "dei:tradingsymbol", "dei:securityexchangename")
ISSUER = "dei:entitycentralindexkey"


@dataclass(frozen=True)
class CoverObservation:
    cik: str
    accession: str
    context: str
    class_title: str
    symbol: str
    exchange_display: str
    accepted_at: datetime
    available_at: datetime
    source_sha256: str


@dataclass(frozen=True)
class CoverAudit:
    observations: tuple[CoverObservation, ...]
    issues: tuple[str, ...]
    transform_version: str = "r3-sec-cover-observations-v1"


class _CoverParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[tuple[str, str], set[str]] = {}
        self.active: tuple[str, str] | None = None
        self.parts: list[str] = []
        self.issues: set[str] = set()
        self.excluded = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "ix:exclude" and self.active is not None:
            self.excluded += 1
        if tag != "ix:nonnumeric":
            return
        if self.active is not None:
            self.issues.add("nested_inline_fact")
            return
        name = (attributes.get("name") or "").lower()
        if name not in (*FIELDS, ISSUER):
            return
        context = attributes.get("contextref") or ""
        if not context:
            self.issues.add("missing_context")
        # Retain visible exchange text, not a normalized exchange code.
        display_exchange = (
            name == "dei:securityexchangename" and attributes.get("format") == "ixt-sec:exchnameen"
        )
        if any(key in attributes for key in ("continuedat", "xsi:nil")) or (
            "format" in attributes and not display_exchange
        ):
            self.issues.add("unsupported_inline_encoding")
        self.active = (context, name)
        self.parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "ix:exclude" and self.excluded:
            self.excluded -= 1
        if tag == "ix:nonnumeric" and self.active is not None:
            value = " ".join("".join(self.parts).split())
            self.values.setdefault(self.active, set()).add(value)
            self.active = None

    def handle_data(self, data: str) -> None:
        if self.active is not None and not self.excluded:
            self.parts.append(data)


def audit_sec_cover(
    payload: bytes,
    *,
    expected_sha256: str,
    cik: str,
    accession: str,
    accepted_at: datetime,
    processing_latency_hours: int = 24,
) -> CoverAudit:
    """Extract complete same-context triples with explicit availability.

    Hash/metadata errors raise. Unsupported encoding/issuer errors reject the
    filing. Incomplete or conflicting contexts are reported and not extracted;
    valid contexts remain separate. Debt is never assumed to be common equity.
    Exchange text is the visible disclosure, not a normalized exchange code.
    """
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("source hash mismatch")
    if len(cik) != 10 or not cik.isascii() or not cik.isdigit():
        raise ValueError("expected ten-digit CIK")
    if not accession or accepted_at.utcoffset() is None or processing_latency_hours < 0:
        raise ValueError("accession, aware acceptance and nonnegative latency required")
    parser = _CoverParser()
    parser.feed(payload.decode("utf-8"))
    parser.close()
    if parser.active is not None:
        parser.issues.add("unterminated_inline_fact")
    issuer_values = {
        value.zfill(10)
        for (_, name), values in parser.values.items()
        if name == ISSUER
        for value in values
    }
    if issuer_values != {cik}:
        parser.issues.add("missing_or_conflicting_issuer")
    contexts = sorted({context for context, name in parser.values if name in FIELDS})
    if not contexts:
        parser.issues.add("no_cover_security_contexts")
    filing_invalid = bool(parser.issues)
    observations: list[CoverObservation] = []
    for context in contexts:
        fields = [parser.values.get((context, name), set()) for name in FIELDS]
        if any(len(values) != 1 or "" in values for values in fields):
            parser.issues.add(f"incomplete_or_conflicting_context:{context}")
            continue
        title, symbol, exchange = (next(iter(values)) for values in fields)
        observations.append(
            CoverObservation(
                cik,
                accession,
                context,
                title,
                symbol,
                exchange,
                accepted_at,
                accepted_at + timedelta(hours=processing_latency_hours),
                expected_sha256,
            )
        )
    return CoverAudit(() if filing_invalid else tuple(observations), tuple(sorted(parser.issues)))


def available_cover_observations(
    audits: tuple[CoverAudit, ...], cutoff: datetime
) -> tuple[CoverObservation, ...]:
    """Select published observations, without extending them into mapping intervals."""
    if cutoff.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")
    return tuple(
        sorted(
            (row for audit in audits for row in audit.observations if row.available_at <= cutoff),
            key=lambda row: (row.available_at, row.cik, row.accession, row.context),
        )
    )
