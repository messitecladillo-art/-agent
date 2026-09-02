#!/usr/bin/env python3
"""Validate a solver run manifest and its reproducibility declarations."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Sequence


SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
SCHEMA = "run-manifest/v2"


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("manifest root must be an object")
    return value


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = PurePosixPath(value.replace("\\", "/"))
    return not parsed.is_absolute() and ".." not in parsed.parts


def validate(manifest: Mapping[str, Any], *, strict: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    if manifest.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA}")
    for key in ("run_id", "input_revision", "code_revision", "route_revision", "command", "cwd"):
        if not isinstance(manifest.get(key), str) or not str(manifest[key]).strip():
            errors.append(f"{key} is required")

    environment = manifest.get("environment")
    if not isinstance(environment, Mapping):
        errors.append("environment must be an object")
        environment = {}
    if not isinstance(environment.get("interpreter"), str) or not environment["interpreter"].strip():
        errors.append("environment.interpreter is required")
    for key in ("packages", "solver_versions"):
        if not isinstance(environment.get(key), list):
            errors.append(f"environment.{key} must be a list")

    seed_policy = manifest.get("seed_policy")
    if not isinstance(seed_policy, Mapping):
        errors.append("seed_policy must be an object")
        seed_policy = {}
    deterministic = seed_policy.get("deterministic")
    if not isinstance(deterministic, bool):
        errors.append("seed_policy.deterministic must be boolean")
    if not isinstance(seed_policy.get("seeds"), list):
        errors.append("seed_policy.seeds must be a list")
    if not isinstance(seed_policy.get("random_sources"), list):
        errors.append("seed_policy.random_sources must be a list")
    random_sources = seed_policy.get("random_sources", [])
    seeds = seed_policy.get("seeds", [])
    if isinstance(random_sources, list) and random_sources and not seeds:
        errors.append("random sources require at least one recorded seed")
    if deterministic is True and random_sources:
        warnings.append("deterministic_run_declares_random_sources")

    checkpoints = manifest.get("checkpoints")
    if not isinstance(checkpoints, list) or not checkpoints:
        errors.append("checkpoints must be a non-empty list")
    else:
        for index, item in enumerate(checkpoints):
            if not isinstance(item, Mapping):
                errors.append(f"checkpoints[{index}] must be an object")
                continue
            for key in ("name", "status"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"checkpoints[{index}].{key} is required")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
        artifacts = []
    artifact_paths: set[str] = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, Mapping):
            errors.append(f"artifacts[{index}] must be an object")
            continue
        path = item.get("path")
        if not _safe_relative(path):
            errors.append(f"artifacts[{index}].path must be a safe relative path")
        elif path in artifact_paths:
            errors.append(f"duplicate_artifact:{path}")
        else:
            artifact_paths.add(str(path))
        digest = item.get("sha256", item.get("hash"))
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest.strip()):
            errors.append(f"artifacts[{index}].sha256 must be a SHA-256 digest")
        for key in ("media_type", "produced_by"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"artifacts[{index}].{key} is required")

    exit_code = manifest.get("exit_code")
    if not isinstance(exit_code, int):
        errors.append("exit_code must be an integer")
    elif exit_code != 0:
        errors.append(f"solver_exit_code:{exit_code}")
    for key in ("stdout_sha256", "stderr_sha256"):
        value = manifest.get(key)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value.strip()):
            errors.append(f"{key} must be a SHA-256 digest")

    status = str(manifest.get("status", "DRAFT")).upper()
    if status in {"VERIFIED", "INDEPENDENTLY_REPRODUCED", "RELEASE_CANDIDATE", "RELEASED"}:
        for index, item in enumerate(checkpoints if isinstance(checkpoints, list) else []):
            if isinstance(item, Mapping) and str(item.get("status", "")).upper() not in {"PASS", "VERIFIED"}:
                errors.append(f"verified_status_with_failed_checkpoint:{index}")
    if strict and warnings:
        errors.extend(warnings)
    unique_errors = list(dict.fromkeys(errors))
    return {
        "schema_version": "run-manifest-validation/v1",
        "valid": not unique_errors,
        "status": "REPRODUCED" if not unique_errors and not warnings else ("BLOCKED" if unique_errors else "PENDING_RESOLUTION"),
        "errors": unique_errors,
        "warnings": list(dict.fromkeys(warnings)),
        "run_id": manifest.get("run_id"),
        "input_revision": manifest.get("input_revision"),
        "artifact_count": len(artifacts),
        "exit_code": exit_code,
        "artifact_paths": sorted(artifact_paths),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        result = validate(_load(args.manifest), strict=args.strict)
    except Exception as exc:
        result = {"schema_version": "run-manifest-validation/v1", "valid": False, "errors": [str(exc)], "warnings": []}
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"valid={result['valid']} status={result.get('status','BLOCKED')}")
        for label in ("errors", "warnings"):
            for item in result.get(label, []):
                print(f"{label[:-1].upper()}: {item}")
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
