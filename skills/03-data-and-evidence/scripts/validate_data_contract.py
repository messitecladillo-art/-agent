#!/usr/bin/env python3
"""Validate a data-and-evidence contract without loading or altering data."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Sequence


SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
SCHEMA = "data-contract/v2"


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("contract root must be an object")
    return value


def _safe_repo_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.replace("\\", "/")
    parsed = PurePosixPath(candidate)
    return not parsed.is_absolute() and ".." not in parsed.parts


def validate(contract: Mapping[str, Any], *, strict: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    if contract.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA}")
    for key in ("dataset_id", "input_revision"):
        if not isinstance(contract.get(key), str) or not str(contract[key]).strip():
            errors.append(f"{key} is required")

    raw_assets = contract.get("raw_assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        errors.append("raw_assets must be a non-empty list")
        raw_assets = []
    raw_paths: set[str] = set()
    for index, item in enumerate(raw_assets):
        if not isinstance(item, Mapping):
            errors.append(f"raw_assets[{index}] must be an object")
            continue
        path = item.get("path")
        if not _safe_repo_path(path):
            errors.append(f"raw_assets[{index}].path must be a safe relative path")
        else:
            normalized = str(path).replace("\\", "/")
            if normalized in raw_paths:
                errors.append(f"duplicate_raw_asset:{normalized}")
            raw_paths.add(normalized)
        digest = item.get("sha256", item.get("hash"))
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest.strip()):
            errors.append(f"raw_assets[{index}].sha256 must be a SHA-256 digest")
        if item.get("immutable") is not True:
            errors.append(f"raw_assets[{index}] must declare immutable=true")
        if not isinstance(item.get("source_ref"), str) or not item["source_ref"].strip():
            errors.append(f"raw_assets[{index}].source_ref is required")

    fields = contract.get("fields")
    if not isinstance(fields, list) or not fields:
        errors.append("fields must be a non-empty list")
        fields = []
    field_names: set[str] = set()
    for index, item in enumerate(fields):
        if not isinstance(item, Mapping):
            errors.append(f"fields[{index}] must be an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"fields[{index}].name is required")
            continue
        if name in field_names:
            errors.append(f"duplicate_field:{name}")
        field_names.add(name)
        for key in ("role", "dtype", "unit", "time_grain", "spatial_grain", "source_ref"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"fields[{index}].{key} is required (use unknown explicitly when unresolved)")
        for key in ("missing_policy", "outlier_policy"):
            if not isinstance(item.get(key), (str, Mapping)):
                errors.append(f"fields[{index}].{key} is required")

    splits = contract.get("splits")
    if not isinstance(splits, Mapping):
        errors.append("splits must be an object")
        splits = {}
    strategy = splits.get("strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        errors.append("splits.strategy is required")
    for key in ("train_refs", "validation_refs", "test_refs", "leakage_checks"):
        if not isinstance(splits.get(key), list):
            errors.append(f"splits.{key} must be a list")
    if strategy and any(token in strategy.lower() for token in ("random", "shuffle")):
        if splits.get("time_cutoff") or splits.get("group_key"):
            warnings.append("random_strategy_with_time_or_group_structure_needs_justification")
    if "time" in str(strategy).lower() and not splits.get("time_cutoff"):
        errors.append("time-aware split requires time_cutoff")
    if "group" in str(strategy).lower() and not splits.get("group_key"):
        errors.append("group-aware split requires group_key")
    leakage_checks = splits.get("leakage_checks", [])
    if isinstance(leakage_checks, list):
        for index, check in enumerate(leakage_checks):
            if not isinstance(check, Mapping):
                errors.append(f"leakage_checks[{index}] must be an object")
                continue
            if check.get("status") not in {"PASS", "WARN", "PENDING", "NOT_APPLICABLE"}:
                errors.append(f"leakage_checks[{index}].status is invalid")
            if check.get("status") != "PASS":
                warnings.append(f"leakage_check_not_pass:{index}")

    quality = contract.get("quality")
    if not isinstance(quality, Mapping):
        errors.append("quality must be an object")
        quality = {}
    for key in ("row_count_reconciliation", "duplicate_check", "missing_report", "anomaly_report"):
        if key not in quality:
            errors.append(f"quality.{key} is required")
    range_checks = quality.get("range_checks")
    if not isinstance(range_checks, list):
        errors.append("quality.range_checks must be a list")

    # A data contract should not claim that an unverified transform is
    # harmless.  Requiring a provenance string for every transform catches
    # silent preprocessing that would otherwise leak into a paper.
    for index, item in enumerate(fields):
        if isinstance(item, Mapping) and item.get("transform") not in (None, "", "identity"):
            if not isinstance(item.get("transform_source_ref"), str) or not item["transform_source_ref"].strip():
                errors.append(f"fields[{index}].transform_source_ref required for non-identity transform")

    if strict and warnings:
        errors.extend(warnings)
    unique_errors = list(dict.fromkeys(errors))
    return {
        "schema_version": "data-contract-validation/v1",
        "valid": not unique_errors,
        "status": "CONTRACTED" if not unique_errors and not warnings else ("BLOCKED" if unique_errors else "PENDING_RESOLUTION"),
        "errors": unique_errors,
        "warnings": list(dict.fromkeys(warnings)),
        "dataset_id": contract.get("dataset_id"),
        "input_revision": contract.get("input_revision"),
        "raw_asset_count": len(raw_assets),
        "field_count": len(fields),
        "split_strategy": strategy,
        "raw_paths": sorted(raw_paths),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        result = validate(_load(args.contract), strict=args.strict)
    except Exception as exc:
        result = {"schema_version": "data-contract-validation/v1", "valid": False, "errors": [str(exc)], "warnings": []}
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
