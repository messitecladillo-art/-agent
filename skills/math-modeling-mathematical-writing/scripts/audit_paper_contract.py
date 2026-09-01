#!/usr/bin/env python3
"""Validate the shared contract used by the mathematical-writing Skill.

The checker validates provenance and dependency structure only.  It deliberately
does not attempt to prove an equation or judge whether a model is scientifically
appropriate.  JSON is supported with the standard library; YAML is supported
when PyYAML is installed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set


REQUIRED_TOP = {"schema", "input_revision", "problem_contract", "variables", "equations", "claims"}
STATUS_OK = {"VERIFIED", "OBSERVED"}
KNOWN_SCHEMA_PREFIXES = ("paper-contract/", "paper-contract", "v1")
EXTERNAL_REF_PREFIXES = ("data:", "kbdoc:", "kbchunk:", "repo:", "source:", "artifact:", "env:", "paper:", "section:")


@dataclass
class Issue:
    code: str
    severity: str
    location: str
    message: str


def load_document(path: Path) -> Mapping[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        value = json.loads(raw)
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("YAML input requires PyYAML; use JSON or install PyYAML") from exc
        value = yaml.safe_load(raw)
    if not isinstance(value, Mapping):
        raise ValueError("contract root must be an object/map")
    return value


def as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def declared_result_ids(value: Any) -> Set[str]:
    """Accept either ['result:id'] or [{"id": "result:id"}, ...]."""
    result: Set[str] = set()
    for item in as_list(value):
        if isinstance(item, Mapping) and nonempty_string(item.get("id")):
            result.add(str(item["id"]).strip())
        elif nonempty_string(item):
            result.add(str(item).strip())
    return result


def is_known_or_external_ref(value: Any, known: Set[str]) -> bool:
    if not nonempty_string(value):
        return True
    ref = str(value).strip()
    return ref in known or ref.startswith(EXTERNAL_REF_PREFIXES)


def add_required(issues: List[Issue], obj: Mapping[str, Any], fields: Iterable[str], location: str) -> None:
    for field in fields:
        if field not in obj or obj[field] in (None, "", []):
            issues.append(Issue("MISSING_FIELD", "error", location, f"missing required field '{field}'"))


def duplicate_ids(items: Sequence[Any], key: str, issues: List[Issue], section: str) -> Set[str]:
    seen: Dict[str, int] = {}
    values: Set[str] = set()
    for index, item in enumerate(items):
        location = f"{section}[{index}]"
        if not isinstance(item, Mapping):
            issues.append(Issue("ITEM_NOT_OBJECT", "error", location, "entry must be an object/map"))
            continue
        value = item.get(key)
        if not nonempty_string(value):
            issues.append(Issue("MISSING_ID", "error", location, f"'{key}' must be a non-empty string"))
            continue
        value = str(value).strip()
        values.add(value)
        if value in seen:
            issues.append(Issue("DUPLICATE_ID", "error", location,
                                f"{key} '{value}' duplicates {section}[{seen[value]}]"))
        else:
            seen[value] = index
    return values


def audit_contract(data: Mapping[str, Any], *, strict: bool,
                   external_registries: Optional[Sequence[tuple[str, Mapping[str, Any]]]] = None) -> Dict[str, Any]:
    issues: List[Issue] = []
    for field in sorted(REQUIRED_TOP):
        if field not in data:
            issues.append(Issue("MISSING_TOP_FIELD", "error", "root", f"missing top-level field '{field}'"))
    schema = data.get("schema")
    if nonempty_string(schema) and not any(str(schema).startswith(prefix) for prefix in KNOWN_SCHEMA_PREFIXES):
        issues.append(Issue("UNKNOWN_SCHEMA", "warning", "schema", f"unrecognised schema '{schema}'"))
    revision = data.get("input_revision")
    if not nonempty_string(revision):
        issues.append(Issue("MISSING_REVISION", "error", "input_revision", "all registries must share a non-empty input_revision"))
    for location, registry in external_registries or ():
        if not isinstance(registry, Mapping) or not nonempty_string(registry.get("input_revision")):
            issues.append(Issue("MISSING_REVISION", "error", location, "external registry has no input_revision"))
        elif revision and registry.get("input_revision") != revision:
            issues.append(Issue("REVISION_MISMATCH", "error", location,
                                f"external input_revision '{registry.get('input_revision')}' differs from root '{revision}'"))

    problem = data.get("problem_contract")
    sub_ids: Set[str] = set()
    if not isinstance(problem, Mapping):
        issues.append(Issue("BAD_PROBLEM_CONTRACT", "error", "problem_contract", "must be an object/map"))
    else:
        add_required(issues, problem, ("contest", "edition", "group", "problem_id", "subproblems"), "problem_contract")
        subproblems = as_list(problem.get("subproblems"))
        sub_ids = duplicate_ids(subproblems, "id", issues, "problem_contract.subproblems")
        if not subproblems:
            issues.append(Issue("NO_SUBPROBLEMS", "error", "problem_contract.subproblems", "at least one subproblem is required"))
        for index, item in enumerate(subproblems):
            if isinstance(item, Mapping):
                add_required(issues, item, ("objective", "deliverables"), f"problem_contract.subproblems[{index}]")

    variables = as_list(data.get("variables"))
    variable_ids = duplicate_ids(variables, "id", issues, "variables")
    symbols: Dict[str, int] = {}
    for index, item in enumerate(variables):
        location = f"variables[{index}]"
        if not isinstance(item, Mapping):
            continue
        add_required(issues, item, ("symbol", "meaning", "kind", "unit", "status"), location)
        symbol = item.get("symbol")
        if nonempty_string(symbol):
            symbol = str(symbol).strip()
            if symbol in symbols:
                issues.append(Issue("SYMBOL_REUSE", "error", location,
                                    f"symbol '{symbol}' is also declared at variables[{symbols[symbol]}]; use one meaning or an explicit scope"))
            else:
                symbols[symbol] = index
        status = str(item.get("status", ""))
        if status not in {"VERIFIED", "OBSERVED", "CANDIDATE", "HYPOTHESIS", "UNVERIFIED"}:
            issues.append(Issue("UNKNOWN_STATUS", "warning", location, f"unknown variable status '{status}'"))

    assumptions = as_list(data.get("assumptions"))
    assumption_ids = duplicate_ids(assumptions, "id", issues, "assumptions")

    equations = as_list(data.get("equations"))
    equation_ids = duplicate_ids(equations, "id", issues, "equations")
    equation_labels: Dict[str, int] = {}
    for index, item in enumerate(equations):
        location = f"equations[{index}]"
        if not isinstance(item, Mapping):
            continue
        add_required(issues, item, ("label", "question_id", "inputs", "outputs", "domain", "assumptions", "validation_refs", "status"), location)
        label = item.get("label")
        if nonempty_string(label):
            label = str(label).strip()
            if label in equation_labels:
                issues.append(Issue("DUPLICATE_LABEL", "error", location,
                                    f"equation label '{label}' duplicates equations[{equation_labels[label]}]"))
            else:
                equation_labels[label] = index
        question_id = item.get("question_id")
        if nonempty_string(question_id) and sub_ids and str(question_id) not in sub_ids:
            issues.append(Issue("UNKNOWN_QUESTION", "error", location, f"question_id '{question_id}' is not in problem_contract.subproblems"))
        refs = as_list(item.get("inputs")) + as_list(item.get("outputs"))
        known_refs = variable_ids | declared_result_ids(data.get("results"))
        for ref in refs:
            if nonempty_string(ref) and str(ref) not in known_refs:
                issues.append(Issue("UNKNOWN_VARIABLE_REF", "error", location, f"equation refers to undeclared variable/result '{ref}'"))
        unit_check = item.get("unit_check")
        if isinstance(unit_check, Mapping):
            terms = as_list(unit_check.get("terms"))
            operation = str(unit_check.get("operation", "add")).lower()
            if operation in {"add", "sum", "addition"} and len(terms) > 1:
                normalised = {re.sub(r"\s+", "", str(term).lower()) for term in terms}
                if len(normalised) > 1:
                    issues.append(Issue("DIMENSION_MISMATCH", "error", location,
                                        "additive terms have different declared units/dimensions"))
            if str(unit_check.get("status", "")) != "VERIFIED":
                issues.append(Issue("UNIT_UNVERIFIED", "error", location, "equation unit_check.status must be VERIFIED"))
        elif unit_check is None:
            issues.append(Issue("MISSING_UNIT_CHECK", "warning", location, "equation has no unit_check object"))
        if str(item.get("status", "")) not in STATUS_OK:
            issues.append(Issue("EQUATION_UNVERIFIED", "warning", location, "equation is not marked VERIFIED/OBSERVED"))

    crossrefs = data.get("crossrefs", data.get("crossref_manifest", {}))
    if isinstance(crossrefs, Mapping):
        cross_items = as_list(crossrefs.get("items"))
    else:
        cross_items = as_list(crossrefs)
    cross_ids = duplicate_ids(cross_items, "id", issues, "crossrefs")
    cross_labels: Dict[str, int] = {}
    for index, item in enumerate(cross_items):
        location = f"crossrefs[{index}]"
        if not isinstance(item, Mapping):
            continue
        add_required(issues, item, ("kind", "label", "caption", "cited_by", "source_artifact", "generator", "status"), location)
        label = item.get("label")
        if nonempty_string(label):
            label = str(label).strip()
            if label in cross_labels:
                issues.append(Issue("DUPLICATE_LABEL", "error", location,
                                    f"cross-reference label '{label}' duplicates crossrefs[{cross_labels[label]}]"))
            else:
                cross_labels[label] = index
        if not as_list(item.get("cited_by")):
            issues.append(Issue("UNCITED_ARTIFACT", "error", location, "cross-reference must cite a claim or document location"))

    claims = as_list(data.get("claims"))
    claim_ids = duplicate_ids(claims, "id", issues, "claims")
    for index, item in enumerate(claims):
        location = f"claims[{index}]"
        if not isinstance(item, Mapping):
            continue
        add_required(issues, item, ("question_id", "text", "scope", "evidence_refs", "status"), location)
        question_id = item.get("question_id")
        if nonempty_string(question_id) and sub_ids and str(question_id) not in sub_ids:
            issues.append(Issue("UNKNOWN_QUESTION", "error", location, f"claim question_id '{question_id}' is not in problem_contract.subproblems"))
        if not as_list(item.get("evidence_refs")):
            issues.append(Issue("CLAIM_NO_EVIDENCE", "error", location, "claim needs at least one evidence_ref"))
        status = str(item.get("status", ""))
        if strict and status != "VERIFIED":
            issues.append(Issue("CLAIM_NOT_VERIFIED", "error", location, f"strict release requires VERIFIED claim status, got '{status}'"))
        elif status not in {"VERIFIED", "OBSERVED", "UNVERIFIED", "HYPOTHESIS"}:
            issues.append(Issue("UNKNOWN_STATUS", "warning", location, f"unknown claim status '{status}'"))
        if "value" in item and item.get("value") not in (None, ""):
            for field in ("command", "artifact_hash", "validation_refs"):
                if item.get(field) in (None, "", []):
                    issues.append(Issue("CLAIM_NO_PROVENANCE", "error", location, f"numeric claim with value needs '{field}'"))

    validations = data.get("validation", data.get("validation_results", {}))
    validation_items = as_list(validations.get("checks")) if isinstance(validations, Mapping) else as_list(validations)
    validation_ids = duplicate_ids(validation_items, "id", issues, "validation.checks")
    for index, item in enumerate(validation_items):
        location = f"validation.checks[{index}]"
        if not isinstance(item, Mapping):
            continue
        add_required(issues, item, ("kind", "scope", "threshold", "command", "exit_code", "result_hash", "status"), location)
        if item.get("exit_code") not in (0, "0"):
            issues.append(Issue("VALIDATION_FAILED", "error", location, f"validation exit_code is {item.get('exit_code')}"))
        if str(item.get("status", "")) != "VERIFIED":
            issues.append(Issue("VALIDATION_UNVERIFIED", "warning", location, "validation check is not VERIFIED"))

    result_ids = declared_result_ids(data.get("results"))
    known_evidence = set(cross_ids) | set(cross_labels) | set(validation_ids) | set(equation_ids) | result_ids
    for index, item in enumerate(equations):
        if not isinstance(item, Mapping):
            continue
        for ref in as_list(item.get("validation_refs")):
            if nonempty_string(ref) and str(ref) not in validation_ids:
                issues.append(Issue("UNKNOWN_VALIDATION_REF", "error", f"equations[{index}]",
                                    f"validation reference '{ref}' is not declared in validation.checks"))
    for index, item in enumerate(claims):
        if not isinstance(item, Mapping):
            continue
        for field in ("evidence_refs", "validation_refs"):
            for ref in as_list(item.get(field)):
                if not is_known_or_external_ref(ref, known_evidence):
                    issues.append(Issue("UNKNOWN_EVIDENCE_REF", "error", f"claims[{index}]",
                                        f"{field} reference '{ref}' is not declared in the contract"))
    for index, item in enumerate(cross_items):
        if not isinstance(item, Mapping):
            continue
        for ref in as_list(item.get("cited_by")):
            if nonempty_string(ref) and str(ref) not in claim_ids and not str(ref).startswith(EXTERNAL_REF_PREFIXES):
                issues.append(Issue("UNKNOWN_CLAIM_REF", "warning", f"crossrefs[{index}]",
                                    f"cited_by reference '{ref}' is not a declared claim"))

    # Nested registries may carry their own revision.  A mismatch is a hard
    # provenance break; an omitted nested revision is allowed for compact draft
    # contracts because the root revision remains authoritative.
    for section, value in (("problem_contract", problem), ("variables", variables), ("assumptions", assumptions),
                           ("equations", equations), ("crossrefs", cross_items), ("claims", claims),
                           ("validation", validations)):
        nested = value if isinstance(value, Mapping) else None
        if isinstance(nested, Mapping) and nested.get("input_revision") not in (None, "", revision):
            issues.append(Issue("REVISION_MISMATCH", "error", section,
                                f"nested input_revision '{nested.get('input_revision')}' differs from root '{revision}'"))

    # Labels live in one document namespace even when their registry sections
    # are stored separately.  A duplicate label across an equation and a
    # figure is just as dangerous as a duplicate inside one section.
    global_labels: Dict[str, str] = {}
    for section, items in (("equations", equations), ("crossrefs", cross_items)):
        for index, item in enumerate(items):
            if not isinstance(item, Mapping) or not nonempty_string(item.get("label")):
                continue
            label = str(item["label"]).strip()
            location = f"{section}[{index}]"
            if label in global_labels:
                issues.append(Issue("DUPLICATE_GLOBAL_LABEL", "error", location,
                                    f"label '{label}' already declared at {global_labels[label]}"))
            else:
                global_labels[label] = location

    # A registry may explicitly list assumptions in equations without a global
    # assumption section; flag it only as a warning so lightweight contracts are
    # still useful during drafting.
    for index, item in enumerate(equations):
        if isinstance(item, Mapping):
            for assumption in as_list(item.get("assumptions")):
                if nonempty_string(assumption) and assumptions and str(assumption) not in assumption_ids:
                    issues.append(Issue("UNKNOWN_ASSUMPTION_REF", "warning", f"equations[{index}]",
                                        f"assumption '{assumption}' is not declared in assumptions"))

    if strict:
        for issue in issues:
            if issue.severity == "warning":
                issue.severity = "error"
    errors = [item for item in issues if item.severity == "error"]
    warnings = [item for item in issues if item.severity == "warning"]
    return {
        "schema": "paper-contract-audit/v1",
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "status": "FAIL" if errors else ("WARN" if warnings else "PASS"),
            "variables": len(variables),
            "equations": len(equations),
            "claims": len(claims),
            "crossrefs": len(cross_items),
            "validation_checks": len(validation_items),
            "external_registries": len(external_registries or ()),
        },
        "issues": [asdict(item) for item in issues],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="contract JSON or YAML file")
    parser.add_argument("--strict", action="store_true", help="promote warnings and unverified claims to blockers")
    parser.add_argument("--registry", action="append", type=Path, default=[],
                        help="additional registry JSON/YAML; strict mode checks its input_revision")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.path.is_file():
        print(f"audit_paper_contract: file not found: {args.path}", file=sys.stderr)
        return 2
    try:
        data = load_document(args.path)
        external = []
        for registry_path in args.registry:
            external.append((str(registry_path).replace("\\", "/"), load_document(registry_path)))
        report = audit_contract(data, strict=args.strict, external_registries=external)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"audit_paper_contract: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report["summary"]
        print("Paper contract audit: {status} ({errors} errors, {warnings} warnings)".format(**summary))
        for issue in report["issues"]:
            print(f"{issue['severity'].upper():7} {issue['code']:24} {issue['location']} {issue['message']}")
    return 1 if report["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
