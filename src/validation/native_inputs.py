"""Path-derived, content-bound inputs for the trusted native validation path."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.backtest.costs import CostModel
from src.config.settings import AppConfig, load_config
from src.data.canonical_historical import (
    VerifiedCanonicalInputs,
    load_verified_canonical_inputs,
)
from src.validation.provenance import (
    ValidationRunIdentity,
    create_validation_run_identity,
    session_list_sha256,
)


class NativeValidationInputError(ValueError):
    """Raised when native validation identity cannot be derived from exact local content."""


_NATIVE_INPUT_ATTESTATION = object()


@dataclass(frozen=True)
class NativeValidationInputs:
    canonical: VerifiedCanonicalInputs
    config: AppConfig
    validation_spec_path: Path
    strategy_definition_files: tuple[str, ...]
    identity: ValidationRunIdentity
    dataset_certified: bool
    validation_start: date | None
    certification_start: date | None
    universe_policy_sha256: str | None
    dataset_evidence_sha256: str | None
    _attestation: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._attestation is not _NATIVE_INPUT_ATTESTATION:
            raise NativeValidationInputError(
                "native validation inputs must be issued by the path-derived factory"
            )


def _git(repository_root: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise NativeValidationInputError(
            "native validation requires a readable Git worktree"
        ) from error


def _strategy_definition(repository_root: Path) -> tuple[str, tuple[str, ...]]:
    source_root = repository_root / "src"
    files = tuple(
        sorted(
            path.relative_to(repository_root).as_posix()
            for path in source_root.rglob("*.py")
            if path.is_file()
        )
    )
    if not files:
        raise NativeValidationInputError("native strategy definition contains no source files")
    rows = [
        {
            "path": relative,
            "sha256": hashlib.sha256((repository_root / relative).read_bytes()).hexdigest(),
        }
        for relative in files
    ]
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return digest, files


def _certified_policy(
    canonical: VerifiedCanonicalInputs,
    dataset_evidence_path: Path | None,
    universe_policy_path: Path | None,
    canonical_sessions: tuple[date, ...],
) -> tuple[bool, date | None, date | None, str | None, str | None]:
    if dataset_evidence_path is None and universe_policy_path is None:
        return False, None, None, None, None
    if dataset_evidence_path is None or universe_policy_path is None:
        raise NativeValidationInputError(
            "dataset evidence and universe policy must be supplied together"
        )
    try:
        evidence: object = json.loads(dataset_evidence_path.read_text(encoding="utf-8"))
        policy: object = json.loads(universe_policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NativeValidationInputError("producer evidence is unreadable") from error
    if not isinstance(evidence, dict) or not isinstance(policy, dict):
        raise NativeValidationInputError("producer evidence must contain JSON objects")
    if evidence.get("producer_version") != canonical.transformation_version:
        raise NativeValidationInputError("producer version does not match canonical transformation")
    producer_id = evidence.get("producer_id")
    if not isinstance(producer_id, str) or len(producer_id) != 64 or any(
        character not in "0123456789abcdef" for character in producer_id
    ):
        raise NativeValidationInputError("producer identity is invalid")
    policy_hash = policy.get("sha256")
    policy_content = {key: value for key, value in policy.items() if key != "sha256"}
    observed_policy_hash = hashlib.sha256(
        json.dumps(policy_content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if policy_hash != observed_policy_hash:
        raise NativeValidationInputError("universe policy content hash does not match")
    required_checks = (
        "source_manifest_validated",
        "membership_identity_validated",
        "corporate_actions_validated",
        "independent_membership_audit_validated",
    )
    if any(evidence.get(name) is not True for name in required_checks):
        raise NativeValidationInputError("dataset evidence is not fully certified")
    if evidence.get("dataset_manifest_sha256") != canonical.manifest_sha256:
        raise NativeValidationInputError("dataset evidence does not match canonical manifest")
    if evidence.get("universe_policy_sha256") != policy_hash:
        raise NativeValidationInputError("dataset evidence does not match universe policy")
    evidence_directory = dataset_evidence_path.parent
    report_files = {
        "membership_audit_sha256": evidence_directory / "membership_audit.json",
        "semantic_report_sha256": evidence_directory / "semantic_report.json",
    }
    for evidence_key, report_path in report_files.items():
        try:
            report_bytes = report_path.read_bytes()
        except OSError as error:
            raise NativeValidationInputError(
                f"certification report is unreadable: {report_path.name}"
            ) from error
        if hashlib.sha256(report_bytes).hexdigest() != evidence.get(evidence_key):
            raise NativeValidationInputError(
                f"certification report hash does not match: {report_path.name}"
            )
    try:
        audit = json.loads(report_files["membership_audit_sha256"].read_text())
        semantic = json.loads(report_files["semantic_report_sha256"].read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise NativeValidationInputError("certification report is unreadable") from error
    if not isinstance(audit, dict) or not isinstance(semantic, dict):
        raise NativeValidationInputError("certification reports must contain JSON objects")
    sample_size = audit.get("requested_sample_size")
    events = audit.get("audited_events")
    sources = audit.get("independent_sources")
    corroborated = audit.get("corroborated_events")
    minimum = audit.get("minimum_corroborated_events")
    if (
        audit.get("passed") is not True
        or isinstance(sample_size, bool)
        or not isinstance(sample_size, int)
        or not 50 <= sample_size <= 100
        or not isinstance(events, list)
        or len(events) != sample_size
        or not isinstance(sources, list)
        or len(set(sources)) < 2
        or isinstance(corroborated, bool)
        or not isinstance(corroborated, int)
        or isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or corroborated < minimum
    ):
        raise NativeValidationInputError("membership audit report is not admissible")
    event_ids = [
        row.get("event", {}).get("event_id")
        for row in events
        if isinstance(row, dict) and isinstance(row.get("event"), dict)
    ]
    if (
        len(event_ids) != sample_size
        or any(not value for value in event_ids)
        or len(set(event_ids)) != sample_size
    ):
        raise NativeValidationInputError("membership audit events are incomplete or duplicated")
    if semantic.get("passed") is not True or semantic.get("findings") != []:
        raise NativeValidationInputError("semantic certification report is not passing")
    try:
        validation_start = date.fromisoformat(str(policy["validation_start"]))
        certification_start = date.fromisoformat(str(policy["certification_start"]))
        floor = int(policy["minimum_investable_constituents"])
        session_counts = policy["session_counts"]
    except (KeyError, TypeError, ValueError) as error:
        raise NativeValidationInputError(
            "universe policy eligibility fields are invalid"
        ) from error
    if not isinstance(session_counts, list) or floor < 1:
        raise NativeValidationInputError("universe policy session counts are invalid")
    benchmark_count = semantic.get("benchmark_session_count")
    expected_benchmark_count = sum(1 for day in canonical_sessions if day >= certification_start)
    if benchmark_count != expected_benchmark_count:
        raise NativeValidationInputError(
            "semantic report benchmark coverage does not match canonical data"
        )
    parsed_counts: dict[date, int] = {}
    try:
        for row in session_counts:
            if not isinstance(row, dict):
                raise ValueError
            session = date.fromisoformat(str(row["session"]))
            count = row["price_eligible_constituents"]
            if isinstance(count, bool) or not isinstance(count, int) or session in parsed_counts:
                raise ValueError
            parsed_counts[session] = count
    except (KeyError, TypeError, ValueError) as error:
        raise NativeValidationInputError("universe policy session counts are invalid") from error
    required_sessions = tuple(day for day in canonical_sessions if day >= validation_start)
    applicable = {day: count for day, count in parsed_counts.items() if day >= validation_start}
    if set(applicable) != set(required_sessions) or any(
        applicable[day] < floor for day in required_sessions
    ):
        raise NativeValidationInputError("universe policy does not sustain its eligibility floor")
    if certification_start >= validation_start:
        raise NativeValidationInputError("universe certification must precede validation")
    evidence_hash = hashlib.sha256(dataset_evidence_path.read_bytes()).hexdigest()
    return True, validation_start, certification_start, str(policy_hash), evidence_hash


def create_native_validation_inputs(
    *,
    canonical_manifest_path: Path,
    config_path: Path,
    validation_spec_path: Path,
    repository_root: Path,
    strategy_version: str,
    dataset_evidence_path: Path | None = None,
    universe_policy_path: Path | None = None,
) -> NativeValidationInputs:
    """Load exact files and derive the parent identity without caller-supplied hashes."""
    canonical = load_verified_canonical_inputs(canonical_manifest_path)
    config = load_config(config_path)
    universe = config.values.get("universe")
    if not isinstance(universe, dict) or universe.get("source") != "trusted_canonical":
        raise NativeValidationInputError(
            "native validation requires universe.source=trusted_canonical"
        )
    try:
        spec_bytes = validation_spec_path.read_bytes()
    except OSError as error:
        raise NativeValidationInputError("validation specification is unreadable") from error
    if not spec_bytes:
        raise NativeValidationInputError("validation specification must not be empty")
    strategy_sha256, strategy_files = _strategy_definition(repository_root.resolve())
    revision = _git(repository_root.resolve(), "rev-parse", "HEAD")
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise NativeValidationInputError("Git revision is not canonical")
    dirty = bool(_git(repository_root.resolve(), "status", "--porcelain"))
    sessions = tuple(
        sorted({bar.date for bar in canonical.bars if bar.symbol == config.benchmark})
    )
    if not sessions:
        raise NativeValidationInputError("canonical benchmark has no sessions")
    (
        dataset_certified,
        validation_start,
        certification_start,
        policy_hash,
        evidence_hash,
    ) = _certified_policy(canonical, dataset_evidence_path, universe_policy_path, sessions)
    baseline = CostModel(*config.transaction_costs)
    stressed = CostModel(*config.stress_transaction_costs)
    identity = create_validation_run_identity(
        canonical_manifest_sha256=canonical.manifest_sha256,
        config_sha256=config.sha256,
        strategy_version=strategy_version,
        strategy_definition_sha256=strategy_sha256,
        baseline_costs=baseline,
        stressed_costs=stressed,
        calendar_sessions_sha256=session_list_sha256(sessions),
        validation_spec_sha256=hashlib.sha256(spec_bytes).hexdigest(),
        git_revision=revision,
        git_dirty=dirty,
        dataset_evidence_sha256=evidence_hash,
        universe_policy_sha256=policy_hash,
    )
    return NativeValidationInputs(
        canonical,
        config,
        validation_spec_path.resolve(),
        strategy_files,
        identity,
        dataset_certified,
        validation_start,
        certification_start,
        policy_hash,
        evidence_hash,
        _NATIVE_INPUT_ATTESTATION,
    )
