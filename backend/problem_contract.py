"""Conservative, deterministic extraction of a mathematical modelling prompt.

This module deliberately does *not* solve or interpret a problem.  It emits a
draft contract whose text-derived fields are ``observed`` and whose archetype
ranking is only a ``hypothesis`` for later review.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


VERSION = "problem-contract/v1"
STATUS = "DRAFT_UNVERIFIED"

_DELIVERY_VERBS = (
    "建立", "构建", "设计", "制定", "求解", "优化", "预测", "估计", "计算",
    "分析", "评价", "评估", "比较", "确定", "给出", "提出", "验证", "模拟",
    "calculate", "compute", "estimate", "predict", "optimize", "design",
    "build", "construct", "analyze", "analyse", "evaluate", "compare", "validate",
)
_DATA_WORDS = ("数据", "附件", "样本", "记录", "观测", "调查", "指标", "dataset", "data", "sample", "observations")
_VALIDATION_WORDS = ("验证", "检验", "稳健", "敏感性", "误差", "精度", "回测", "交叉验证", "validate", "validation", "test", "robust", "sensitivity")
_CONSTRAINT_WORDS = ("约束", "限制", "不超过", "至少", "至多", "不得", "必须", "满足", "范围", "上限", "下限", "constraint", "limit", "at most", "at least")

_ARCHETYPES = {
    "prediction": ("预测", "回归", "分类", "概率", "forecast", "predict", "regression", "classification"),
    "optimization": ("最优", "优化", "调度", "分配", "路径", "约束", "optimal", "optimize", "scheduling", "allocation"),
    "mechanism": ("扩散", "传热", "守恒", "动力学", "边界", "输运", "diffusion", "heat", "conservation", "dynamics"),
    "simulation": ("仿真", "模拟", "情景", "随机", "排队", "simulation", "stochastic", "queue"),
    "policy-decision": ("政策", "方案", "影响", "风险", "决策", "policy", "impact", "risk", "decision"),
}


def _claim(value: Any, kind: str = "observed", *, evidence: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    return {"value": value, "claim_class": kind, "evidence_refs": list(evidence or [])}


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[。！？!?；;])\s*|\n+", text) if s.strip()]


def _unique(items: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(x for x in items if x))


def _verbs(text: str) -> List[str]:
    lowered = text.lower()
    return _unique(v for v in _DELIVERY_VERBS if v.lower() in lowered)


def _variables(text: str) -> List[str]:
    # Symbols are cues, not a claim that they are model variables.
    found = re.findall(r"(?<![A-Za-z])[A-Za-z](?:_[A-Za-z0-9]+|[0-9]+)?(?![A-Za-z])", text)
    found += re.findall(r"(?:变量|指标|参数|决策变量)[：:为是]?\s*([^，。；;\n]+)", text)
    return _unique(x.strip() for x in found)


def _prompt_items(text: str, words: Sequence[str]) -> List[str]:
    return [s for s in _sentences(text) if any(w.lower() in s.lower() for w in words)]


def _segments(text: str) -> List[tuple[str, str]]:
    # Numbered headings are boundaries; retain the heading in the observed excerpt.
    marks = list(re.finditer(r"(?im)(?<!\w)(?:问题\s*[一二三四五六七八九十百]+|(?:Q|Question)\s*\d+|[（(]\s*[1-9]\d*\s*[）)])\s*[：:.)、-]?", text))
    if not marks:
        return [("Q1", text.strip())] if text.strip() else []
    out: List[tuple[str, str]] = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        label = mark.group(0).strip(" ：:.)、-（）()")
        out.append((label or f"Q{i + 1}", text[mark.start():end].strip()))
    return out


def build_problem_contract(text: str, source_refs: Optional[Sequence[Any]] = None) -> Dict[str, Any]:
    """Build a serialisable draft contract from arbitrary Chinese/English text."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    refs = list(source_refs or [])
    canonical = json.dumps({"text": text, "source_refs": refs}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    revision = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    evidence = [str(r) for r in refs]
    all_sentences = _sentences(text)
    subs: List[Dict[str, Any]] = []
    for index, (label, segment) in enumerate(_segments(text), 1):
        vars_ = _variables(segment)
        constraints = _prompt_items(segment, _CONSTRAINT_WORDS)
        data = _prompt_items(segment, _DATA_WORDS)
        validation = _prompt_items(segment, _VALIDATION_WORDS)
        delivery = _claim(_verbs(segment), evidence=evidence)
        validations = _claim(validation or ["unknown"], evidence=evidence)
        subs.append({
            "id": label if re.match(r"(?i)^(?:q|question)\s*\d+$", label) else f"Q{index}",
            "prompt_excerpt": _claim(segment, evidence=evidence),
            "delivery_verbs": delivery,
            "deliverable_verbs": delivery,
            "variables": _claim(vars_ or ["unknown"], evidence=evidence),
            "constraints": _claim(constraints or ["unknown"], evidence=evidence),
            "data_prompts": _claim(data or ["unknown"], evidence=evidence),
            "validation_prompts": validations,
            "validation_hints": validations,
        })
    joined = text.lower()
    suggestions = []
    for archetype, cues in _ARCHETYPES.items():
        matched = _unique(cue for cue in cues if cue.lower() in joined)
        suggestions.append({"id": archetype, "matched_cues": matched, "score": len(matched), "claim_class": "hypothesis", "note": "cue-based suggestion; requires independent review"})
    suggestions.sort(key=lambda x: (-x["score"], x["id"]))
    return {
        "contract_version": VERSION,
        "status": STATUS,
        "provenance_status": STATUS,
        "source_refs": evidence,
        "source_refs_claim": _claim(evidence, evidence=evidence),
        "revision": revision,
        "revision_hash": revision,
        "text_summary": _claim({"sentence_count": len(all_sentences), "character_count": len(text)}, evidence=evidence),
        "subproblems": subs,
        "archetype_cue_suggestions": suggestions,
        "uncertainties": ["语义、单位、题目范围和事实真值均未独立核验"],
    }


extract_problem_contract = build_problem_contract
parse_problem_contract = build_problem_contract

__all__ = ["VERSION", "STATUS", "build_problem_contract", "extract_problem_contract", "parse_problem_contract"]
