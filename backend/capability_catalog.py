"""Pure, composable capability catalogue for mathematical-modelling agents.

The catalogue is deliberately metadata-only.  It converts an already obtained
knowledge-base summary into a small routing catalogue; it never scans files,
executes user code, or treats a method card as a claim about a source paper.
Built-in cards are ``curated/inferred`` playbook metadata and must be verified
against the current problem and evidence ledger before use in a paper.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


CATALOG_VERSION = "capability-catalog/v1"


@dataclass(frozen=True)
class MethodCard:
    id: str
    title: str
    family: str
    source_kind: str = "curated/inferred"
    applicability: Tuple[str, ...] = ()
    prohibitions: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    inputs: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ()
    validation: Tuple[str, ...] = ()
    fallback: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowBlock:
    id: str
    title: str
    kind: str
    input_ports: Mapping[str, str] = field(default_factory=dict)
    output_ports: Mapping[str, str] = field(default_factory=dict)
    required_inputs: Tuple[str, ...] = ()
    evidence_output: str = ""
    required: bool = False
    composable: bool = True
    agent_roles: Tuple[str, ...] = ()
    validation_kinds: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowPreset:
    id: str
    title: str
    description: str
    block_ids: Tuple[str, ...]
    archetype_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ProblemArchetype:
    id: str
    title: str
    cues: Tuple[str, ...]
    preferred_blocks: Tuple[str, ...]
    validation_kinds: Tuple[str, ...]
    forbidden_shortcuts: Tuple[str, ...]


@dataclass(frozen=True)
class ContentPack:
    """A reusable, source-oriented bundle for the free assembly canvas."""

    id: str
    title: str
    note: str
    query: str
    applies_to: Tuple[str, ...] = ()
    required_evidence: Tuple[str, ...] = ()
    source_kind: str = "curated/inferred"


@dataclass(frozen=True)
class Catalog:
    version: str
    source: Mapping[str, Any]
    methods: Tuple[MethodCard, ...]
    blocks: Tuple[WorkflowBlock, ...]
    presets: Tuple[WorkflowPreset, ...]
    archetypes: Tuple[ProblemArchetype, ...]
    content_packs: Tuple[ContentPack, ...] = ()


# These are product guardrails, not claims about any particular paper.  A
# custom composition may omit them only as a deliberate draft; the validator
# reports the omission as a blocker instead of silently treating the chain as
# complete.
REQUIRED_BLOCK_IDS = frozenset({"problem-decomposition", "baseline-model", "validation", "writing"})


def _method(
    id: str, title: str, family: str, applicability: Sequence[str],
    prohibitions: Sequence[str], assumptions: Sequence[str], inputs: Sequence[str],
    outputs: Sequence[str], validation: Sequence[str], fallback: Sequence[str],
) -> MethodCard:
    return MethodCard(
        id=id, title=title, family=family, applicability=tuple(applicability),
        prohibitions=tuple(prohibitions), assumptions=tuple(assumptions),
        inputs=tuple(inputs), outputs=tuple(outputs), validation=tuple(validation),
        fallback=tuple(fallback), evidence_refs=(f"playbook:method-card:{id}",),
    )


BUILTIN_METHODS: Tuple[MethodCard, ...] = (
    _method("linear-regression", "线性/岭回归", "statistical", ["连续响应", "可解释系数"], ["明显非线性且无变换"], ["误差结构可诊断", "特征无严重泄漏"], ["data_contract"], ["prediction", "coefficient"], ["holdout", "residual"], ["robust-regression", "gradient-boosting"]),
    _method("logistic-regression", "逻辑回归", "classification", ["二分类概率", "需要可解释 odds"], ["多分类未做扩展"], ["logit 关系可接受", "样本标签已冻结"], ["data_contract"], ["probability", "classification"], ["stratified-holdout", "calibration"], ["random-forest", "gradient-boosting"]),
    _method("random-forest", "随机森林", "ensemble", ["非线性表格数据", "混合特征"], ["把特征重要性当因果"], ["训练样本代表部署域", "树深受控"], ["data_contract"], ["prediction", "feature_importance"], ["holdout", "permutation"], ["gradient-boosting", "linear-regression"]),
    _method("gradient-boosting", "梯度提升树", "ensemble", ["非线性预测", "中小型表格数据"], ["外推到训练域外"], ["损失函数匹配目标", "调参使用隔离验证"], ["data_contract"], ["prediction", "error_curve"], ["cross-validation", "holdout"], ["random-forest", "linear-regression"]),
    _method("arima-forecast", "ARIMA/状态空间预测", "time-series", ["单变量或低维时间序列", "需要滚动预测"], ["打乱时间顺序切分"], ["平稳化或差分可解释", "时间戳无泄漏"], ["time_series_contract"], ["forecast", "interval"], ["rolling-backtest", "residual"], ["exponential-smoothing", "gradient-boosting"]),
    _method("cox-survival", "Cox 生存模型", "survival", ["删失时间到事件", "风险比解释"], ["忽略删失机制"], ["比例风险近似", "事件定义稳定"], ["survival_contract"], ["hazard", "survival_curve"], ["censoring-check", "calibration"], ["parametric-survival", "random-forest"]),
    _method("linear-programming", "线性规划", "optimization", ["线性目标和约束", "资源分配"], ["非线性约束直接线性化而无误差界"], ["参数和单位一致", "可行域非空"], ["model_contract", "constraints"], ["decision", "objective"], ["feasibility", "optimality-gap"], ["integer-programming", "heuristic-search"]),
    _method("integer-programming", "整数/混合整数规划", "optimization", ["离散决策", "指派/选址/排程"], ["规模超出求解器边界却无 gap"], ["整数语义明确", "约束完整"], ["model_contract", "constraints"], ["decision", "bound"], ["feasibility", "optimality-gap"], ["linear-programming", "heuristic-search"]),
    _method("nsga2-multiobjective", "NSGA-II 多目标优化", "optimization", ["冲突目标", "需要 Pareto 前沿"], ["只报一个未解释权重解"], ["目标可比较或已归一化", "约束处理明确"], ["model_contract", "constraints"], ["pareto_front", "decision"], ["feasibility", "sensitivity"], ["weighted-sum", "integer-programming"]),
    _method("heuristic-search", "启发式/元启发式搜索", "optimization", ["非凸或组合空间", "精确法不可承受"], ["声称全局最优无界或基线"], ["编码与约束修复稳定", "随机种子冻结"], ["model_contract", "constraints"], ["candidate_solution", "objective"], ["repeat-seeds", "feasibility"], ["integer-programming", "local-search"]),
    _method("finite-difference-pde", "有限差分 PDE", "mechanism", ["扩散/传热/输运", "网格可定义"], ["边界初值不明或不守恒"], ["连续介质近似", "稳定性条件满足"], ["mechanism_contract", "boundary_conditions"], ["field", "flux"], ["conservation", "grid-convergence"], ["finite-element-pde", "reduced-order-model"]),
    _method("runge-kutta-ode", "Runge–Kutta 常微分方程", "mechanism", ["状态随时间演化", "右端可计算"], ["刚性系统无步长策略"], ["初值和参数可识别", "时间步误差受控"], ["mechanism_contract", "initial_state"], ["trajectory", "state"], ["time-step-convergence", "invariant-check"], ["implicit-ode", "finite-difference-pde"]),
    _method("monte-carlo", "蒙特卡洛模拟", "simulation", ["不确定性传播", "随机场景"], ["重复次数不足却报稳定概率"], ["随机分布有来源", "种子与置信区间记录"], ["model_contract", "random_inputs"], ["scenario_metrics", "interval"], ["replicate-seeds", "confidence-interval"], ["quasi-monte-carlo", "discrete-event-simulation"]),
    _method("discrete-event-simulation", "离散事件仿真", "simulation", ["排队/流程/资源竞争", "事件规则明确"], ["把单次轨迹当结论"], ["事件优先级明确", "暖机和重复策略预设"], ["process_contract", "scenario"], ["throughput", "waiting_time"], ["replicate-seeds", "warmup-sensitivity"], ["monte-carlo", "queueing-approximation"]),
    _method("lhs-sensitivity", "拉丁超立方敏感性", "validation", ["参数扰动筛查", "模型可重复运行"], ["参数范围无物理依据"], ["扰动域覆盖实际不确定性", "指标预先定义"], ["model_contract", "parameter_ranges"], ["sensitivity_report", "ranked_drivers"], ["repeat-seeds", "range-perturbation"], ["one-at-a-time-sensitivity", "bootstrap"]),
    _method("bootstrap-uncertainty", "Bootstrap 不确定性", "validation", ["有限样本估计不确定性", "可重采样数据"], ["时间依赖数据直接独立重采样"], ["重采样方案匹配数据结构", "重复次数足够"], ["data_contract", "estimator"], ["interval", "stability_report"], ["bootstrap-replicates", "holdout"], ["cross-validation", "jackknife"]),
)


BUILTIN_BLOCKS: Tuple[WorkflowBlock, ...] = (
    WorkflowBlock("problem-decomposition", "题面拆解", "problem", {"problem_contract": "problem"}, {"subproblems": "subproblems", "evidence": "evidence"}, ("problem_contract",), "problem_contract", True, True, ("scope",), ("scope_lock",)),
    WorkflowBlock("data-audit", "数据审计", "data", {"subproblems": "subproblems", "dataset": "dataset"}, {"data_contract": "data_contract", "evidence": "evidence"}, (), "data_contract", False, True, ("data_auditor",), ("schema", "leakage",)),
    WorkflowBlock("parameter-contract", "参数与约束契约", "contract", {"subproblems": "subproblems", "data_contract": "data_contract"}, {"model_contract": "model_contract", "constraints": "constraints", "mechanism_spec": "mechanism_spec", "parameter_ranges": "parameter_ranges", "evidence": "evidence"}, ("subproblems",), "model_contract", False, True, ("scope", "domain"), ("units", "identifiability", "constraints",)),
    WorkflowBlock("scenario-contract", "情景与边界契约", "contract", {"subproblems": "subproblems", "data_contract": "data_contract", "mechanism_spec": "mechanism_spec"}, {"scenario": "scenario", "boundary_conditions": "boundary_conditions", "initial_state": "initial_state", "evidence": "evidence"}, ("subproblems",), "scenario", False, True, ("domain", "simulation"), ("boundary", "initial_state",)),
    WorkflowBlock("baseline-model", "基线模型", "baseline", {"data_contract": "data_contract", "subproblem": "subproblems"}, {"model": "model", "result": "result"}, ("data_contract",), "", True, True, ("solver",), ("baseline",)),
    WorkflowBlock("mechanism-model", "机制模型", "mechanism", {"data_contract": "data_contract", "mechanism_spec": "mechanism_spec"}, {"model": "model", "result": "result"}, ("mechanism_spec",), "", False, True, ("domain", "solver"), ("dimension", "conservation",)),
    WorkflowBlock("optimization", "优化求解", "optimization", {"model": "model", "constraints": "constraints"}, {"solution": "result", "evidence": "evidence"}, ("model", "constraints"), "solution", False, True, ("algorithm",), ("feasibility", "optimality_gap")),
    WorkflowBlock("simulation", "情景仿真", "simulation", {"model": "model", "scenario": "scenario"}, {"result": "result", "evidence": "evidence"}, ("model", "scenario"), "result", False, True, ("simulation",), ("replicate", "confidence_interval")),
    WorkflowBlock("validation", "题型验证", "validation", {"model": "model", "result": "result", "baseline": "result"}, {"validation_report": "validation_report", "evidence": "evidence"}, ("model", "result"), "validation_report", True, True, ("validation",), ("at_least_two_families",)),
    WorkflowBlock("sensitivity", "敏感性分析", "validation", {"model": "model", "result": "result", "parameter_ranges": "parameter_ranges"}, {"sensitivity_report": "sensitivity_report", "evidence": "evidence"}, ("model", "result", "parameter_ranges"), "sensitivity_report", False, True, ("validation",), ("sensitivity",)),
    WorkflowBlock("critic-challenger", "独立质疑与反例", "review", {"model": "model", "result": "result", "validation_report": "validation_report"}, {"critique_report": "critique_report", "evidence": "evidence"}, ("model", "result"), "critique_report", False, True, ("critic", "challenger"), ("counterexample", "assumption_break",)),
    WorkflowBlock("writing", "论文写作", "writing", {"subproblems": "subproblems", "result": "result", "validation_report": "validation_report", "critique_report": "critique_report"}, {"paper_claims": "paper_claims", "paper_draft": "paper_draft"}, ("subproblems", "result", "validation_report"), "paper_claims", True, True, ("writer",), ("claim_evidence",)),
    WorkflowBlock("defense", "答辩准备", "defense", {"paper_draft": "paper_draft", "validation_report": "validation_report"}, {"defense_pack": "defense_pack"}, ("paper_draft", "validation_report"), "", False, True, ("writer",), ("qa",)),
)


BUILTIN_ARCHETYPES: Tuple[ProblemArchetype, ...] = (
    ProblemArchetype("prediction", "预测/统计", ("预测", "回归", "分类", "概率"), ("problem-decomposition", "data-audit", "parameter-contract", "baseline-model", "validation", "critic-challenger", "sensitivity", "writing"), ("holdout", "residual", "calibration"), ("random-split-time-series", "r2-as-guarantee")),
    ProblemArchetype("optimization", "优化/运筹", ("最优", "调度", "分配", "路径", "约束"), ("problem-decomposition", "data-audit", "parameter-contract", "baseline-model", "optimization", "validation", "critic-challenger", "sensitivity", "writing"), ("feasibility", "optimality-gap", "sensitivity"), ("single-objective-without-tradeoff", "unreported-infeasibility")),
    ProblemArchetype("mechanism", "机制/物理", ("扩散", "传热", "守恒", "动力学", "边界"), ("problem-decomposition", "data-audit", "parameter-contract", "scenario-contract", "mechanism-model", "simulation", "validation", "critic-challenger", "sensitivity", "writing"), ("conservation", "boundary", "grid-convergence"), ("dimensionless-omission", "correlation-as-causality")),
    ProblemArchetype("simulation", "仿真/随机过程", ("排队", "仿真", "情景", "随机", "到达"), ("problem-decomposition", "data-audit", "parameter-contract", "scenario-contract", "baseline-model", "simulation", "validation", "critic-challenger", "sensitivity", "writing"), ("replicate-seeds", "confidence-interval", "warmup"), ("single-run-conclusion", "unseeded-randomness")),
    ProblemArchetype("policy-decision", "政策/决策", ("政策", "方案", "影响", "风险", "决策"), ("problem-decomposition", "data-audit", "parameter-contract", "baseline-model", "optimization", "critic-challenger", "sensitivity", "validation", "writing", "defense"), ("scenario-perturbation", "robustness", "identifiability"), ("causal-overclaim", "unbounded-extrapolation")),
)


BUILTIN_PRESETS: Tuple[WorkflowPreset, ...] = (
    WorkflowPreset("standard-cumcm", "标准国赛建模流程", "题面—数据—参数/情景契约—基线/机制—求解—独立质疑—验证—敏感性—论文—答辩", tuple(block.id for block in BUILTIN_BLOCKS), tuple(a.id for a in BUILTIN_ARCHETYPES)),
    WorkflowPreset("data-to-paper", "数据驱动快线", "适合预测或表格决策题，保留参数契约、透明基线、独立质疑和双验证", ("problem-decomposition", "data-audit", "parameter-contract", "baseline-model", "validation", "critic-challenger", "sensitivity", "writing"), ("prediction", "optimization")),
    WorkflowPreset("mechanism-simulation", "机制仿真线", "适合守恒、动力学和情景仿真题，先锁定参数、边界与情景，再以透明基线对照复现", ("problem-decomposition", "data-audit", "parameter-contract", "scenario-contract", "baseline-model", "mechanism-model", "simulation", "validation", "critic-challenger", "sensitivity", "writing", "defense"), ("mechanism", "simulation")),
)


BUILTIN_CONTENT_PACKS: Tuple[ContentPack, ...] = (
    ContentPack("problem-evidence", "题面证据", "题面、附件、单位与约束", "历年赛题 附件 约束 单位", ("all",), ("problem_contract", "source_refs")),
    ContentPack("paper-structure", "范文结构", "问题分析、模型链、验证章节", "优秀论文 问题分析 模型假设 验证", ("all",), ("paper_outline", "claim_evidence")),
    ContentPack("method-code", "方法与代码", "算法入口、参数与复现线索", "模型算法 代码 参数 复现", ("all",), ("run_command", "result_hash")),
    ContentPack("counterexample", "反例与边界", "敏感性、失败模式、禁用条件", "敏感性分析 误差 适用条件 反例", ("all",), ("prohibitions", "independent_review")),
    ContentPack("paper-template", "写作模板", "摘要、三线表、排版与答辩", "论文模板 写作规范 三线表 答辩", ("all",), ("format_check", "claim_index")),
)


def _serialise(items: Iterable[Any]) -> List[Dict[str, Any]]:
    return [asdict(item) for item in items]


def metadata_snapshot_to_catalog(snapshot: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Convert an existing KB metadata snapshot without opening its files."""
    snapshot = snapshot or {}
    source = {
        "source_status": snapshot.get("source_status", "UNAVAILABLE"),
        "index_revision": snapshot.get("index_revision"),
        "root_id": snapshot.get("root_id"),
        "catalog_consistent": bool(snapshot.get("catalog_consistent", False)),
        "facets": dict(snapshot.get("facets") or {}),
        "indexed_count": snapshot.get("indexed_count", snapshot.get("valid_count", 0)),
        "warnings": list(snapshot.get("warnings") or []),
        "usage_note": "Built-in capability cards are curated/inferred playbook metadata, not source-text facts.",
    }
    return {
        "catalog_version": CATALOG_VERSION,
        "source": source,
        "methods": _serialise(BUILTIN_METHODS),
        "workflow_blocks": _serialise(BUILTIN_BLOCKS),
        "workflow_presets": _serialise(BUILTIN_PRESETS),
        "problem_archetypes": _serialise(BUILTIN_ARCHETYPES),
        "content_packs": _serialise(BUILTIN_CONTENT_PACKS),
    }


def _lookup_blocks(blocks: Sequence[WorkflowBlock]) -> Dict[str, WorkflowBlock]:
    return {block.id: block for block in blocks}


def _normalise_edge(edge: Any) -> Optional[Tuple[str, str, str, str]]:
    """Convert tuple/dict edge forms into one stable comparison shape."""
    if isinstance(edge, Mapping):
        values = (
            edge.get("source", edge.get("from")),
            edge.get("source_port", edge.get("from_port")),
            edge.get("target", edge.get("to")),
            edge.get("target_port", edge.get("to_port")),
        )
    else:
        try:
            values = tuple(edge)
        except (TypeError, ValueError):
            return None
    if len(values) != 4 or not all(isinstance(item, str) for item in values):
        return None
    return tuple(values)  # type: ignore[return-value]


def _normalise_node(node: Any) -> Optional[Dict[str, Any]]:
    """Return the fields that affect an assembly revision/diff."""
    if isinstance(node, Mapping):
        node_id = node.get("node_id", node.get("id"))
        block_id = node.get("block_id")
        if not isinstance(node_id, str) or not isinstance(block_id, str):
            return None
        return {
            "node_id": node_id,
            "block_id": block_id,
            "method_id": node.get("method_id"),
            "label": node.get("label"),
            "config": dict(node.get("config") or {}),
        }
    return None


def composition_diff(
    previous_nodes: Optional[Sequence[Mapping[str, Any]]] = None,
    previous_edges: Optional[Sequence[Any]] = None,
    current_nodes: Optional[Sequence[Mapping[str, Any]]] = None,
    current_edges: Optional[Sequence[Any]] = None,
    *,
    required_block_ids: Iterable[str] = REQUIRED_BLOCK_IDS,
    previous_innovation: Optional[Mapping[str, Any]] = None,
    current_innovation: Optional[Mapping[str, Any]] = None,
    previous_content_pack_ids: Optional[Sequence[str]] = None,
    current_content_pack_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Describe an assembly change without executing or trusting its nodes.

    The result is intentionally a small, deterministic audit record.  It is
    suitable for an append-only event payload and for a UI diff; it does not
    decide whether a mathematical model is correct.
    """
    before_rows = [row for row in (_normalise_node(item) for item in (previous_nodes or [])) if row]
    after_rows = [row for row in (_normalise_node(item) for item in (current_nodes or [])) if row]
    before = {row["node_id"]: row for row in before_rows}
    after = {row["node_id"]: row for row in after_rows}
    added_ids = sorted(set(after) - set(before))
    removed_ids = sorted(set(before) - set(after))
    changed = []
    for node_id in sorted(set(before).intersection(after)):
        if before[node_id] != after[node_id]:
            changed.append({"node_id": node_id, "before": before[node_id], "after": after[node_id]})
    before_edge_rows = sorted({_normalise_edge(item) for item in (previous_edges or []) if _normalise_edge(item) is not None})
    after_edge_rows = sorted({_normalise_edge(item) for item in (current_edges or []) if _normalise_edge(item) is not None})
    before_edge_keys = set(before_edge_rows)
    after_edge_keys = set(after_edge_rows)
    added_edges = [list(edge) for edge in sorted(after_edge_keys - before_edge_keys)]
    removed_edges = [list(edge) for edge in sorted(before_edge_keys - after_edge_keys)]
    impacted = set(added_ids) | set(removed_ids) | {row["node_id"] for row in changed}
    for edge in added_edges + removed_edges:
        impacted.update((edge[0], edge[2]))
    required = sorted(set(str(item) for item in required_block_ids))
    present = {row["block_id"] for row in after_rows}
    missing = [block_id for block_id in required if block_id not in present]
    # Innovation is an auditable difference card, not a release claim.  Keep
    # the comparison in the same deterministic diff so a reviewer can see
    # whether a revision changed the graph, the proposed novelty, or both.
    before_innovation = dict(previous_innovation or {})
    after_innovation = dict(current_innovation or {})
    innovation_changed = before_innovation != after_innovation
    innovation_fields = sorted(set(before_innovation) | set(after_innovation))
    changed_innovation_fields = [
        field for field in innovation_fields
        if before_innovation.get(field) != after_innovation.get(field)
    ]
    innovation_missing = [
        field for field in ("baseline", "difference", "necessity", "boundary", "validation")
        if not str(after_innovation.get(field, "")).strip()
    ] if after_innovation else ["baseline", "difference", "necessity", "boundary", "validation"]
    innovation_gate = {
        "present": bool(after_innovation),
        "ready": bool(after_innovation) and not innovation_missing,
        "status": "READY_FOR_REVIEW" if bool(after_innovation) and not innovation_missing else "DRAFT_UNVERIFIED",
        "missing": innovation_missing,
        "claim_class": "hypothesis",
    }
    before_packs = sorted({str(item) for item in (previous_content_pack_ids or []) if str(item).strip()})
    after_packs = sorted({str(item) for item in (current_content_pack_ids or []) if str(item).strip()})
    content_pack_added = sorted(set(after_packs) - set(before_packs))
    content_pack_removed = sorted(set(before_packs) - set(after_packs))
    content_pack_changed = bool(content_pack_added or content_pack_removed)
    return {
        "schema_version": "assembly-diff/v1",
        "changed": bool(added_ids or removed_ids or changed or added_edges or removed_edges or innovation_changed or content_pack_changed),
        "added_nodes": [after[node_id] for node_id in added_ids],
        "removed_nodes": [before[node_id] for node_id in removed_ids],
        "changed_nodes": changed,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
        "impacted_nodes": sorted(impacted),
        "required_block_ids": required,
        "missing_required_blocks": missing,
        "innovation_changed": innovation_changed,
        "changed_innovation_fields": changed_innovation_fields,
        "innovation_gate": innovation_gate,
        "content_pack_added": content_pack_added,
        "content_pack_removed": content_pack_removed,
        "content_pack_changed": content_pack_changed,
        "content_pack_ids": after_packs,
        "status": "BLOCKED" if missing else "READY_FOR_REVIEW",
        "claim_class": "derived",
    }


def validate_composition(
    nodes: Mapping[str, str],
    edges: Sequence[Tuple[str, str, str, str]],
    *,
    blocks: Sequence[WorkflowBlock] = BUILTIN_BLOCKS,
) -> Dict[str, Any]:
    """Validate a user-composed workflow DAG and return an inspectable report.

    Edge format is ``(source_node, source_port, target_node, target_port)``.
    Port types must match exactly.  A composition must include a validation
    block, and if writing is present it must receive a validation report.
    """
    errors: List[str] = []
    block_map = _lookup_blocks(blocks)
    for node_id, block_id in nodes.items():
        if block_id not in block_map:
            errors.append(f"unknown_block:{node_id}:{block_id}")
    incoming: Dict[str, List[Tuple[str, str]]] = {node: [] for node in nodes}
    adjacency: Dict[str, List[str]] = {node: [] for node in nodes}
    normalised_edges: List[Tuple[str, str, str, str]] = []
    for edge in edges:
        if isinstance(edge, Mapping):
            src = edge.get("from", edge.get("source"))
            src_port = edge.get("from_port", edge.get("source_port"))
            dst = edge.get("to", edge.get("target"))
            dst_port = edge.get("to_port", edge.get("target_port"))
        else:
            try:
                src, src_port, dst, dst_port = edge
            except (TypeError, ValueError):
                errors.append(f"invalid_edge:{edge!r}")
                continue
        if not all(isinstance(item, str) for item in (src, src_port, dst, dst_port)):
            errors.append(f"invalid_edge:{edge!r}")
            continue
        normalised_edges.append((src, src_port, dst, dst_port))
        if src not in nodes or dst not in nodes:
            errors.append(f"unknown_node:{src}->{dst}")
            continue
        src_block, dst_block = block_map.get(nodes[src]), block_map.get(nodes[dst])
        if src_block is None or dst_block is None:
            continue
        src_type = src_block.output_ports.get(src_port)
        dst_type = dst_block.input_ports.get(dst_port)
        if src_type is None:
            errors.append(f"unknown_output_port:{src}:{src_port}")
        if dst_type is None:
            errors.append(f"unknown_input_port:{dst}:{dst_port}")
        if src_type is not None and dst_type is not None and src_type != dst_type:
            errors.append(f"port_type_mismatch:{src}.{src_port}->{dst}.{dst_port}")
        if dst in incoming:
            incoming[dst].append((dst_port, src))
        adjacency[src].append(dst)
    for node_id, block_id in nodes.items():
        block = block_map.get(block_id)
        if block is None:
            continue
        connected = {port for port, _ in incoming[node_id]}
        for required in block.required_inputs:
            if required not in connected and block_id != "problem-decomposition":
                errors.append(f"required_input_missing:{node_id}:{required}")
    # DFS cycle detection and stable topological order.
    visiting: set[str] = set()
    visited: set[str] = set()
    topo: List[str] = []
    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"cycle:{node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for nxt in adjacency[node]:
            visit(nxt)
        visiting.remove(node)
        visited.add(node)
        topo.append(node)
    for node in nodes:
        visit(node)
    if not any(block_map.get(block_id, WorkflowBlock("", "", "")).kind == "validation" for block_id in nodes.values()):
        errors.append("required_validation_node_missing")
    validation_nodes = [node for node, block_id in nodes.items() if block_id == "validation"]
    writing_nodes = [node for node, block_id in nodes.items() if block_id == "writing"]
    if writing_nodes and not any(any(port == "validation_report" for port, _ in incoming[node]) for node in writing_nodes):
        errors.append("evidence_chain_missing:validation_to_writing")
    # A validation node must be downstream of at least one model-producing node.
    model_nodes = {node for node, block_id in nodes.items() if block_id in {"baseline-model", "mechanism-model", "optimization", "simulation"}}
    reachable = set()
    frontier = list(model_nodes)
    while frontier:
        current = frontier.pop()
        for nxt in adjacency.get(current, []):
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)
    if validation_nodes and not any(node in reachable for node in validation_nodes):
        errors.append("evidence_chain_missing:model_to_validation")
    topo.reverse()
    required_ids = sorted(REQUIRED_BLOCK_IDS)
    present_ids = set(nodes.values())
    missing_required = [block_id for block_id in required_ids if block_id not in present_ids]
    # Keep this as a separate hard-gate projection so callers can distinguish a
    # structural port error from an intentionally incomplete draft.  The
    # historical ``valid`` field remains the structural verdict used by older
    # adapters; missing product gates are also included in ``errors`` so a new
    # caller cannot accidentally promote the draft.
    for block_id in missing_required:
        errors.append(f"required_block_missing:{block_id}")
    unique_errors = list(dict.fromkeys(errors))
    custom_ids = sorted(present_ids.difference(REQUIRED_BLOCK_IDS))
    return {
        "valid": not unique_errors,
        "errors": unique_errors,
        "topological_order": topo,
        "node_count": len(nodes),
        "edge_count": len(normalised_edges),
        "required_block_ids": required_ids,
        "present_required_blocks": [block_id for block_id in required_ids if block_id in present_ids],
        "missing_required_blocks": missing_required,
        "custom_block_ids": custom_ids,
        "hard_gate": {
            "ready": not missing_required,
            "status": "READY_FOR_REVIEW" if not missing_required else "BLOCKED",
            "missing": missing_required,
        },
    }


def compose_workflow(
    nodes: Mapping[str, str],
    edges: Sequence[Tuple[str, str, str, str]],
    *,
    blocks: Sequence[WorkflowBlock] = BUILTIN_BLOCKS,
) -> Dict[str, Any]:
    """Return a serialisable composition or raise on an invalid graph."""
    report = validate_composition(nodes, edges, blocks=blocks)
    if not report["valid"]:
        raise ValueError("invalid workflow composition: " + "; ".join(report["errors"]))
    serial_edges = []
    for edge in edges:
        if isinstance(edge, Mapping):
            serial_edges.append(dict(edge))
        else:
            serial_edges.append(tuple(edge))
    return {"nodes": dict(nodes), "edges": serial_edges, "validation": report}


# Small aliases keep adapter code readable while preserving one implementation.
build_capability_catalog = metadata_snapshot_to_catalog
validate_workflow = validate_composition


__all__ = [
    "CATALOG_VERSION", "Catalog", "MethodCard", "WorkflowBlock", "WorkflowPreset", "ProblemArchetype", "ContentPack",
    "REQUIRED_BLOCK_IDS",
    "BUILTIN_METHODS", "BUILTIN_BLOCKS", "BUILTIN_PRESETS", "BUILTIN_ARCHETYPES", "BUILTIN_CONTENT_PACKS",
    "metadata_snapshot_to_catalog", "build_capability_catalog", "validate_composition", "validate_workflow", "compose_workflow", "composition_diff",
]
