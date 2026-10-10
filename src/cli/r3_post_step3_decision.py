"""Materialize the immutable post-Step-3 remediation decision package."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from importlib import metadata
from pathlib import Path

from src.config.r3_post_step3 import load_r3_post_step3_config
from src.research.r3_post_step3_decision import (
    build_decision_artifacts,
    canonical_bytes,
    sha256_bytes,
    sha256_file,
    validate_decision_artifacts,
    write_new,
)


def _git(*args: str) -> str:
    return subprocess.check_output(("git", *args), text=True).strip()


def _implementation_manifest() -> list[dict[str, str]]:
    paths = set(_git("ls-files").splitlines())
    paths.update(_git("ls-files", "--others", "--exclude-standard").splitlines())
    output: list[dict[str, str]] = []
    for name in sorted(path for path in paths if path):
        source = Path(name)
        if source.is_file():
            output.append({"path": name, "sha256": sha256_file(source)})
    return output


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ("PyYAML", "pyarrow", "numpy", "scikit-learn"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not_installed"
    return versions


def materialize(config_path: Path, output: Path) -> dict[str, str]:
    if output.exists():
        raise FileExistsError(f"immutable package path already exists: {output}")
    config = load_r3_post_step3_config(config_path)
    implementation = _implementation_manifest()
    status = _git("status", "--porcelain=v1")
    provenance: dict[str, object] = {
        "provenance_version": "r3-post-step3-environment-v1",
        "run_timestamp": config.run_timestamp,
        "seed": config.seed,
        "git_revision": _git("rev-parse", "HEAD"),
        "git_committed_tree": _git("rev-parse", "HEAD^{tree}"),
        "git_dirty": bool(status),
        "git_status_sha256": sha256_bytes((status + "\n").encode()),
        "dirty_state_identity": sha256_bytes(
            canonical_bytes({"status": status.splitlines(), "implementation": implementation})
        ),
        "implementation_tree_sha256": sha256_bytes(canonical_bytes(implementation)),
        "implementation_files": implementation,
        "config_path": config_path.as_posix(),
        "config_file_sha256": sha256_file(config_path),
        "typed_config_sha256": config.sha256,
        "bound_configuration_hashes": {
            path.as_posix(): sha256_file(path)
            for path in (
                Path("config.r3.yaml"),
                Path("config.r3-development.yaml"),
                Path("config.r3-step3-feasibility.yaml"),
                config_path,
            )
        },
        "python": platform.python_version(),
        "dependencies": _dependency_versions(),
        "xgboost": "not_installed_or_inspected; not required for this decision step",
        "randomness_used": False,
        "seeds": [config.seed, 20261002, 20260926],
        "scope": "evidence verification and governance records only",
    }
    artifacts = build_decision_artifacts(config, provenance=provenance)
    validate_decision_artifacts(artifacts)
    output.mkdir(parents=True)
    hashes: dict[str, str] = {}
    try:
        for name, value in artifacts.items():
            hashes[name] = write_new(output / name, value)
        package_identity = sha256_bytes(canonical_bytes(hashes))
        manifest = {
            "manifest_version": "r3-post-step3-artifact-hashes-v1",
            "package_identity": package_identity,
            "artifacts": hashes,
        }
        hashes["artifact_hash_manifest.json"] = write_new(
            output / "artifact_hash_manifest.json", manifest
        )
    except Exception:
        # An incomplete directory remains visible and is never silently reused.
        raise
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    hashes = materialize(args.config, args.output_directory)
    manifest = json.loads(
        (args.output_directory / "artifact_hash_manifest.json").read_text(encoding="utf-8")
    )
    print(
        json.dumps(
            {"package_identity": manifest["package_identity"], "hashes": hashes}, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
