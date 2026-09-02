#!/usr/bin/env python3
"""Audit structural invariants in a LaTeX mathematics paper.

This is intentionally a conservative, dependency-free checker.  It does not
parse or prove mathematics; it catches the cheap-to-detect failures that make
derivations hard to review: duplicate/unresolved labels, missing metadata,
manual equation numbers, and unfinished placeholders.  Use a real LaTeX
engine and an independent mathematical review for semantic correctness.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


DISPLAY_ENVS = {
    "equation",
    "align",
    "alignat",
    "gather",
    "multline",
    "flalign",
    "displaymath",
    "math",
}
NUMBERED_DISPLAY_ENVS = DISPLAY_ENVS - {"displaymath", "math"}
FLOAT_ENVS = {"figure", "figure*", "table", "table*"}
LABEL_RE = re.compile(r"(?<!\\)\\label\s*\{([^{}]+)\}")
REF_RE = re.compile(r"(?<!\\)\\(?:eqref|ref|pageref|autoref|cref|Cref)\s*\{([^{}]+)\}")
BEGIN_RE = re.compile(r"\\begin\s*\{([A-Za-z*]+)\}")
END_RE = re.compile(r"\\end\s*\{([A-Za-z*]+)\}")
CAPTION_RE = re.compile(r"(?<!\\)\\caption(?:\[[^\]]*\])?\s*\{", re.S)
TAG_RE = re.compile(r"(?<!\\)\\tag\s*\{([^{}]*)\}")
PLACEHOLDER_RE = re.compile(r"TODO|FIXME|TBD|待填|待补|未完成|\?\?\?", re.I)
PREFIX_RE = re.compile(r"^(?:eq|eqn|fig|tbl|tab|alg|app|sec|def|claim|val|asm|sub|prop|lem|thm|remark|lst|code):")


@dataclass
class Issue:
    code: str
    severity: str
    path: str
    line: int
    message: str


@dataclass
class LabelOccurrence:
    name: str
    path: str
    line: int


@dataclass
class EnvironmentOccurrence:
    name: str
    path: str
    start_line: int
    end_line: int
    labels: List[str]
    has_caption: bool


def strip_comments(text: str) -> str:
    """Remove LaTeX comments while preserving newlines and line positions."""
    rows: List[str] = []
    for raw in text.splitlines(keepends=True):
        cut = None
        for index, char in enumerate(raw):
            if char != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and raw[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                cut = index
                break
        rows.append(raw if cut is None else raw[:cut] + ("\n" if raw.endswith("\n") else ""))
    return "".join(rows)


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def read_tex(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def collect_files(target: Path) -> List[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".tex" else []
    if target.is_dir():
        return sorted(item for item in target.rglob("*.tex") if item.is_file())
    raise FileNotFoundError(str(target))


def parse_environments(text: str, path: str) -> List[EnvironmentOccurrence]:
    """Pair begin/end commands, retaining only environments useful to the audit."""
    tokens: List[Tuple[int, str, str]] = []
    for match in BEGIN_RE.finditer(text):
        tokens.append((match.start(), "begin", match.group(1)))
    for match in END_RE.finditer(text):
        tokens.append((match.start(), "end", match.group(1)))
    tokens.sort(key=lambda item: item[0])

    stack: List[Tuple[str, int]] = []
    result: List[EnvironmentOccurrence] = []
    for offset, kind, name in tokens:
        if kind == "begin":
            stack.append((name, offset))
            continue
        # TeX permits nested environments.  Recover from an unmatched end by
        # closing the nearest same-name opener instead of hiding later errors.
        opener_index = next((i for i in range(len(stack) - 1, -1, -1) if stack[i][0] == name), None)
        if opener_index is None:
            continue
        opened_name, opened_offset = stack.pop(opener_index)
        if opened_name not in DISPLAY_ENVS and opened_name not in FLOAT_ENVS:
            continue
        start_line = line_number(text, opened_offset)
        end_line = line_number(text, offset)
        body = text[opened_offset:offset]
        labels = [m.group(1).strip() for m in LABEL_RE.finditer(body)]
        has_caption = bool(CAPTION_RE.search(body))
        result.append(EnvironmentOccurrence(opened_name, path, start_line, end_line, labels, has_caption))
    return sorted(result, key=lambda item: (item.start_line, item.end_line))


def audit(paths: Sequence[Path], *, strict: bool, require_equation_labels: bool,
          require_float_metadata: bool, forbid_manual_tags: bool,
          check_label_prefixes: bool) -> Dict[str, object]:
    issues: List[Issue] = []
    labels: List[LabelOccurrence] = []
    refs: List[Tuple[str, str, int]] = []
    environments: List[EnvironmentOccurrence] = []
    all_text: List[Tuple[Path, str, str]] = []

    for path in paths:
        raw = read_tex(path)
        text = strip_comments(raw)
        rel = str(path).replace("\\", "/")
        all_text.append((path, raw, text))
        for match in LABEL_RE.finditer(text):
            name = match.group(1).strip()
            labels.append(LabelOccurrence(name, rel, line_number(text, match.start())))
            if check_label_prefixes and not PREFIX_RE.match(name):
                issues.append(Issue("LABEL_PREFIX", "warning", rel, line_number(text, match.start()),
                                    f"label '{name}' has no recognized semantic prefix"))
        for match in REF_RE.finditer(text):
            at_line = line_number(text, match.start())
            for name in match.group(1).split(","):
                name = name.strip()
                if name:
                    refs.append((name, rel, at_line))
        for match in TAG_RE.finditer(text):
            severity = "error" if forbid_manual_tags else "warning"
            issues.append(Issue("MANUAL_TAG", severity, rel, line_number(text, match.start()),
                                "manual \\tag numbering can drift; prefer a semantic label and engine numbering"))
        for match in PLACEHOLDER_RE.finditer(text):
            issues.append(Issue("PLACEHOLDER", "error", rel, line_number(text, match.start()),
                                f"unfinished placeholder '{match.group(0)}'"))
        environments.extend(parse_environments(text, rel))

    by_name: Dict[str, List[LabelOccurrence]] = {}
    for occurrence in labels:
        by_name.setdefault(occurrence.name, []).append(occurrence)
    for name, occurrences in sorted(by_name.items()):
        if len(occurrences) > 1:
            locations = ", ".join(f"{item.path}:{item.line}" for item in occurrences)
            issues.append(Issue("DUPLICATE_LABEL", "error", occurrences[0].path, occurrences[0].line,
                                f"label '{name}' appears {len(occurrences)} times ({locations})"))

    label_names = set(by_name)
    for name, path, line in refs:
        if name not in label_names:
            issues.append(Issue("UNRESOLVED_REF", "error", path, line,
                                f"reference '{name}' has no matching label"))

    for env in environments:
        if env.name in NUMBERED_DISPLAY_ENVS and require_equation_labels and not env.labels:
            severity = "error" if strict else "warning"
            issues.append(Issue("EQUATION_MISSING_LABEL", severity, env.path, env.start_line,
                                f"numbered environment '{env.name}' has no semantic label"))
        if env.name in FLOAT_ENVS and require_float_metadata:
            if not env.has_caption:
                severity = "error" if strict else "warning"
                issues.append(Issue("FLOAT_MISSING_CAPTION", severity, env.path, env.start_line,
                                    f"{env.name} environment has no caption"))
            if not env.labels:
                severity = "error" if strict else "warning"
                issues.append(Issue("FLOAT_MISSING_LABEL", severity, env.path, env.start_line,
                                    f"{env.name} environment has no label"))

    # A strict run treats structural warnings as blockers, but keeps the
    # report severity explicit so callers can distinguish the original rule.
    if strict:
        for issue in issues:
            # Manual tags remain an advisory warning unless the caller opts
            # into --forbid-manual-tags; some official templates deliberately
            # use a custom tag strategy.
            if issue.severity == "warning" and issue.code != "MANUAL_TAG":
                issue.severity = "error"

    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    return {
        "schema": "latex-math-audit/v1",
        "files": [str(path).replace("\\", "/") for path in paths],
        "summary": {
            "files": len(paths),
            "labels": len(labels),
            "references": len(refs),
            "environments": len(environments),
            "errors": len(errors),
            "warnings": len(warnings),
            "status": "FAIL" if errors else ("WARN" if warnings else "PASS"),
        },
        "labels": [asdict(item) for item in labels],
        "references": [{"name": name, "path": path, "line": line} for name, path, line in refs],
        "issues": [asdict(issue) for issue in issues],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="a .tex file or directory to scan recursively")
    parser.add_argument("--strict", action="store_true", help="promote warnings to blocking errors")
    parser.add_argument("--release", action="store_true",
                        help="release profile: strict + equation labels + float metadata + no manual tags")
    parser.add_argument("--require-equation-labels", action="store_true",
                        help="require labels in numbered display environments")
    parser.add_argument("--require-float-metadata", action="store_true",
                        help="require caption and label in every figure/table")
    parser.add_argument("--forbid-manual-tags", action="store_true",
                        help="treat manual \\tag numbering as an error")
    parser.add_argument("--check-label-prefixes", action="store_true",
                        help="warn when labels do not use a semantic prefix")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable JSON report")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = collect_files(args.path)
    except FileNotFoundError:
        print(f"audit_latex_math: path not found: {args.path}", file=sys.stderr)
        return 2
    if not paths:
        print("audit_latex_math: no .tex files found", file=sys.stderr)
        return 2
    release = bool(args.release)
    report = audit(paths, strict=args.strict or release,
                   require_equation_labels=args.require_equation_labels or release,
                   require_float_metadata=args.require_float_metadata or release,
                   forbid_manual_tags=args.forbid_manual_tags or release,
                   check_label_prefixes=args.check_label_prefixes)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report["summary"]
        print("LaTeX math audit: {status} ({errors} errors, {warnings} warnings; {files} files)".format(**summary))
        for issue in report["issues"]:
            print(f"{issue['severity'].upper():7} {issue['code']:24} {issue['path']}:{issue['line']} {issue['message']}")
    return 1 if report["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
