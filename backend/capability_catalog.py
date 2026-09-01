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
    # Canonical workflow kinds accepted by this card.  This additive field is
    # intentionally optional so older callers that construct MethodCard with
    # positional arguments remain valid.  ``family`` is retained as the
    # routing/display label; this field makes the block compatibility explicit
    # for the puzzle assembler and independent auditors.
    compatible_block_kinds: Tuple[str, ...] = ()


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


METHOD_FAMILY_BLOCK_KINDS: Mapping[str, Tuple[str, ...]] = {
    # Baseline/统计 families deliberately share the ``baseline`` kind.  The
    # UI may still display the more specific family when choosing a card.
    "statistical": ("baseline",),
    "classification": ("baseline",),
    "ensemble": ("baseline",),
    "time-series": ("baseline",),
    "survival": ("baseline",),
    "problem": ("problem",),
    "data": ("data",),
    "contract": ("contract",),
    "mechanism": ("mechanism",),
    "optimization": ("optimization",),
    "simulation": ("simulation",),
    "validation": ("validation",),
    "review": ("review",),
    "writing": ("writing",),
    "defense": ("defense",),
}


def _method(
    id: str, title: str, family: str, applicability: Sequence[str],
    prohibitions: Sequence[str], assumptions: Sequence[str], inputs: Sequence[str],
    outputs: Sequence[str], validation: Sequence[str], fallback: Sequence[str],
    compatible_block_kinds: Optional[Sequence[str]] = None,
    evidence_refs: Optional[Sequence[str]] = None,
) -> MethodCard:
    kinds = tuple(compatible_block_kinds or METHOD_FAMILY_BLOCK_KINDS.get(family, ()))
    refs = tuple(evidence_refs or (f"playbook:method-card:{id}",))
    return MethodCard(
        id=id, title=title, family=family, applicability=tuple(applicability),
        prohibitions=tuple(prohibitions), assumptions=tuple(assumptions),
        inputs=tuple(inputs), outputs=tuple(outputs), validation=tuple(validation),
        fallback=tuple(fallback), evidence_refs=refs, compatible_block_kinds=kinds,
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

    # Problem framing cards: they turn a statement into auditable subproblem
    # and deliverable contracts before a solver is selected.
    _method("question-tree-decomposition", "问题树与小问映射", "problem", ["题面含多个小问或多层交付物", "需要逐问回链原句"], ["仅凭关键词猜测隐含目标", "把示例现象当成题面约束"], ["题面版本已锁定", "每个小问有可核对的交付物"], ["problem_contract", "source_refs"], ["subproblems", "deliverable_map", "coverage_matrix"], ["prompt-quote-coverage", "owner-scope-review"], ["manual-scope-lock", "question-checklist"]),
    _method("objective-constraint-ledger", "目标—约束台账", "problem", ["存在多目标、边界或资源约束", "需要区分硬约束与软目标"], ["未经题面证据把偏好写成硬约束", "遗漏不可行条件却直接求解"], ["目标方向和单位可解释", "约束来源可回溯"], ["problem_contract", "source_refs"], ["objective_set", "constraint_ledger", "tradeoff_notes"], ["unit-consistency", "constraint-coverage", "owner-review"], ["scope-lock", "assumption-boundary-ledger"]),
    _method("problem-type-triage", "题型线索分诊", "problem", ["题面尚未确定统计/机制/优化/仿真路线", "需要并列保留候选 archetype"], ["把 cue-match 当作自动选模", "没有证据就排除替代路线"], ["线索来自已锁定题面", "分诊结果标注 hypothesis"], ["problem_contract", "archetype_cues"], ["candidate_archetypes", "route_questions", "triage_warnings"], ["cue-coverage", "independent-triage", "counterexample-question"], ["manual-route-review", "baseline-first"]),

    # Data cards: these create a data contract rather than silently cleaning
    # values inside a downstream model.
    _method("schema-provenance-audit", "模式与来源审计", "data", ["附件含表格、多个文件或字段来源不一", "需要记录类型、单位、粒度和 provenance"], ["未经记录直接覆盖原始值", "将文件名或列名当成语义真值"], ["原始文件只读留存", "每个字段有来源或 unknown 标记"], ["dataset", "source_refs", "problem_contract"], ["data_contract", "variable_registry", "provenance_map"], ["schema-check", "unit-check", "row-count-reconcile"], ["manual-data-dictionary", "quarantine-ambiguous-fields"]),
    _method("missingness-mechanism-audit", "缺失机制与插补审计", "data", ["缺失值影响估计或决策", "可区分 MCAR/MAR/结构性缺失"], ["把缺失编码当作零", "先插补全体数据再切分训练/测试"], ["缺失机制假设显式记录", "插补只使用允许的信息"], ["data_contract", "split_spec", "missingness_profile"], ["imputation_plan", "missingness_report", "uncertainty_flag"], ["mask-holdout", "pattern-check", "sensitivity-to-imputation"], ["complete-case-baseline", "indicator-feature"]),
    _method("leakage-safe-split", "无泄漏切分策略", "data", ["预测/分类/时间序列任务需要隔离评估", "存在主体、时间或组结构"], ["随机打乱时间序列", "让同一主体跨 train/test 泄漏"], ["部署时点与评估窗口已定义", "切分规则可复现"], ["data_contract", "time_index", "group_id"], ["split_spec", "train_set", "test_set", "leakage_report"], ["split-replay", "group-overlap-check", "temporal-order-check"], ["blocked-time-split", "group-cross-validation"]),

    # Contract cards: explicit variables, assumptions, identifiability and
    # scenarios are shared by all downstream puzzle blocks.
    _method("variable-unit-registry", "变量—单位—粒度登记", "contract", ["模型涉及多个量、时间尺度或空间尺度", "论文需要可读的符号表"], ["混用单位而只在结果处修正", "用同一符号表示不同粒度变量"], ["每个变量有唯一含义", "换算因子和观测粒度可追溯"], ["subproblems", "data_contract", "source_refs"], ["variable_registry", "unit_registry", "dimension_map"], ["dimensional-consistency", "symbol-uniqueness", "source-quote-check"], ["manual-symbol-table", "dimensionless-reparameterization"]),
    _method("assumption-boundary-ledger", "假设与禁用边界台账", "contract", ["题面信息不完备或模型有理想化假设", "需要把适用域写进方法链"], ["把方便计算的假设写成事实", "省略失效条件和外推边界"], ["每条假设有理由、影响和检查", "禁用条件可触发 fallback"], ["problem_contract", "variable_registry", "domain_constraints"], ["assumption_registry", "boundary_conditions", "fallback_triggers"], ["assumption-challenge", "parameter-perturbation", "owner-approval"], ["conservative-baseline", "scenario-contract"]),
    _method("identifiability-check", "参数可识别性检查", "contract", ["待估参数多于独立信息", "机制模型或政策模型需要解释参数"], ["用不可识别参数给出确定性结论", "把拟合优度当作可识别性证明"], ["观测设计和参数域已列出", "参数先验/约束有来源"], ["model_contract", "data_contract", "parameter_ranges"], ["identifiability_report", "estimable_parameter_set", "uncertainty_flags"], ["rank-check", "profile-likelihood", "perturbation-recovery"], ["fix-parameter-baseline", "regularization-with-disclosure"]),
    _method("scenario-design-contract", "情景树与边界契约", "contract", ["需要比较政策、资源或环境情景", "边界/初值随情景变化"], ["无来源地外推极端情景", "只报单一路径而不说明范围"], ["情景变量和范围预先冻结", "边界条件在每个情景可复现"], ["subproblems", "data_contract", "mechanism_spec"], ["scenario", "boundary_conditions", "initial_state", "scenario_matrix"], ["scenario-coverage", "boundary-check", "out-of-domain-flag"], ["baseline-scenario", "one-factor-scenarios"]),

    # Transparent baselines and classical statistics.
    _method("descriptive-statistical-baseline", "描述统计与朴素基线", "statistical", ["需要先给出可解释参照", "目标可由均值/中位数/季节性规则表达"], ["把朴素基线当作机制解释", "忽略分组结构和分母定义"], ["指标、分母和评估窗口已冻结", "基线与主模型使用同一切分"], ["data_contract", "split_spec"], ["baseline_model", "baseline_metrics", "reference_table"], ["holdout", "group-summary-reconcile", "metric-definition-check"], ["linear-regression", "seasonal-naive-forecast"]),
    _method("ridge-regression", "岭回归", "statistical", ["连续响应且特征共线", "需要稳定且可解释的线性基线"], ["正则化参数用测试集选择", "将收缩系数解释为因果效应"], ["特征已标准化或尺度记录", "正则化强度用隔离验证选择"], ["data_contract", "split_spec", "feature_matrix"], ["prediction", "coefficient", "regularization_path"], ["cross-validation", "holdout", "residual"], ["linear-regression", "elastic-net"]),
    _method("generalized-linear-model", "广义线性模型", "statistical", ["计数、比例或非正态响应", "链接函数可解释"], ["响应分布与链接函数不匹配", "过度离散却仍用普通方差"], ["分布族和链接函数有题面/数据依据", "独立性或暴露量假设可检查"], ["data_contract", "exposure", "split_spec"], ["prediction", "coefficient", "dispersion_report"], ["deviance-check", "calibration", "residual"], ["linear-regression", "quasi-likelihood"]),
    _method("seasonal-naive-forecast", "季节朴素预测", "time-series", ["存在稳定季节周期", "需要可解释的时间序列基线"], ["周期未确认就复制滞后值", "随机切分破坏时间顺序"], ["周期长度来自数据或题面", "预测窗口严格晚于训练窗口"], ["time_series_contract", "time_index"], ["forecast", "interval", "baseline_metrics"], ["rolling-backtest", "residual", "seasonality-check"], ["arima-forecast", "exponential-smoothing"]),

    # Mechanism cards: each one exposes physical structure and a checkable
    # numerical route; none is a substitute for missing boundary evidence.
    _method("mass-balance-compartment", "质量/库存平衡舱室模型", "mechanism", ["流入—流出—积累可写成守恒方程", "系统可按舱室或节点聚合"], ["无守恒依据却套用平衡式", "忽略源汇项和时间尺度"], ["舱室边界清楚", "参数与初值可识别或有范围"], ["mechanism_spec", "initial_state", "boundary_conditions"], ["state", "flow", "balance_residual"], ["conservation", "initial-condition-replay", "parameter-perturbation"], ["runge-kutta-ode", "finite-difference-pde"]),
    _method("finite-element-pde", "有限元偏微分方程", "mechanism", ["复杂几何或非均匀介质", "边界条件与网格可定义"], ["网格质量/边界未审计", "以单一网格结果宣称收敛"], ["弱形式与材料参数有依据", "网格细化和稳定性策略预先设定"], ["mechanism_contract", "boundary_conditions", "mesh"], ["field", "flux", "mesh_diagnostics"], ["grid-convergence", "conservation", "boundary-residual"], ["finite-difference-pde", "reduced-order-model"]),
    _method("system-dynamics-model", "系统动力学反馈模型", "mechanism", ["存在库存—流量—反馈回路", "需要长期情景演化"], ["相关性直接画成因果回路", "反馈方向和时滞没有证据"], ["因果假设逐条标注", "时间步与饱和边界可复现"], ["mechanism_spec", "scenario", "initial_state"], ["trajectory", "stock_flow_table", "feedback_report"], ["time-step-convergence", "loop-removal-check", "scenario-robustness"], ["mass-balance-compartment", "runge-kutta-ode"]),

    # Optimization cards: preserve feasibility, trade-offs and an explicit
    # optimality/termination story.
    _method("weighted-sum-multiobjective", "加权和多目标规划", "optimization", ["目标冲突但可归一化", "决策者能提供权重情景"], ["量纲未统一就加权", "只报告一个权重而隐藏 Pareto 选择"], ["权重来源和归一化区间已记录", "约束可行域非空"], ["model_contract", "constraints", "objective_set"], ["decision", "objective_values", "tradeoff_table"], ["feasibility", "weight-sensitivity", "pareto-check"], ["nsga2-multiobjective", "goal-programming"]),
    _method("dynamic-programming", "动态规划", "optimization", ["阶段决策具有最优子结构", "状态空间可离散或有界"], ["状态爆炸却无近似误差说明", "不满足马尔可夫性仍递推"], ["状态、动作和转移方程明确", "边界价值和终止条件可复核"], ["model_contract", "constraints", "state_transition"], ["policy", "value_function", "decision"], ["Bellman-residual", "small-instance-enumeration", "feasibility"], ["integer-programming", "heuristic-search"]),
    _method("robust-optimization", "鲁棒优化", "optimization", ["参数区间或场景不确定", "需要最坏情形/预算鲁棒解"], ["不确定集合无来源", "把保守解误称为平均最优"], ["不确定集合和预算已冻结", "鲁棒目标与业务损失一致"], ["model_contract", "constraints", "parameter_ranges", "scenario"], ["robust_decision", "worst_case_bound", "scenario_table"], ["feasibility", "uncertainty-set-sweep", "nominal-vs-robust"], ["linear-programming", "weighted-sum-multiobjective"]),
    _method("local-search-neighborhood", "邻域局部搜索", "optimization", ["组合空间较大且精确求解成本高", "有可行解修复器"], ["把局部最优写成全局最优", "邻域或随机种子未披露"], ["编码、邻域和停止准则固定", "至少有可比基线"], ["model_contract", "constraints", "initial_solution"], ["candidate_solution", "objective_trace", "termination_report"], ["repeat-seeds", "feasibility", "baseline-gap"], ["integer-programming", "heuristic-search"]),

    # Simulation cards: make randomness, warm-up, replication and scenario
    # definitions first-class outputs.
    _method("agent-based-simulation", "基于主体的仿真", "simulation", ["个体规则与异质性驱动总体行为", "需要观察涌现现象"], ["个体规则没有观测/文献依据", "单次轨迹当作普遍规律"], ["主体状态、交互和随机源明确", "种子、重复次数和停止条件冻结"], ["model", "scenario", "agent_rules", "random_inputs"], ["trajectory", "population_metrics", "emergence_report"], ["replicate-seeds", "rule-ablation", "confidence-interval"], ["discrete-event-simulation", "monte-carlo"]),
    _method("queueing-network-simulation", "排队网络仿真", "simulation", ["到达、服务、队列和资源竞争明确", "需要等待时间/吞吐量分布"], ["忽略暖机和容量边界", "把平均等待时间当作每个个体保证"], ["到达/服务分布有来源", "队列纪律和资源优先级已声明"], ["model", "scenario", "arrival_process", "service_process"], ["throughput", "waiting_time", "queue_length_distribution"], ["warmup-sensitivity", "replicate-seeds", "queue-conservation"], ["discrete-event-simulation", "queueing-approximation"]),
    _method("latin-hypercube-scenario-simulation", "拉丁超立方情景采样", "simulation", ["多个连续不确定参数需覆盖组合空间", "单次模型运行成本可控"], ["参数边界任意设定", "样本量不足却排序敏感性"], ["边界/分布和相关性有来源", "采样方案与随机种子记录"], ["model", "scenario", "parameter_ranges", "random_inputs"], ["scenario_metrics", "coverage_map", "uncertainty_interval"], ["coverage-check", "replicate-seeds", "sample-size-stability"], ["monte-carlo", "lhs-sensitivity"]),

    # Validation cards: each is a check, not a model-quality guarantee.
    _method("cross-validation", "交叉验证与嵌套调参", "validation", ["独立同分布或分组数据需要估计泛化误差", "超参数较多"], ["把测试集用于调参", "忽略组/时间结构而随机折叠"], ["折叠规则与指标预先注册", "所有预处理在折内拟合"], ["model", "data_contract", "split_spec"], ["cv_report", "generalization_interval", "selected_config"], ["fold-replay", "nested-holdout", "metric-definition-check"], ["holdout", "group-cross-validation"]),
    _method("rolling-origin-backtest", "滚动起点回测", "validation", ["时间序列、概念漂移或在线预测", "评估窗口按时间推进"], ["随机打乱时间", "用未来信息构造特征"], ["时间戳排序可靠", "训练窗/预测窗和更新频率固定"], ["model", "time_series_contract", "forecast_horizon"], ["backtest_report", "forecast_errors", "drift_flags"], ["temporal-order-check", "rolling-metrics", "residual"], ["blocked-time-split", "seasonal-naive-forecast"]),
    _method("residual-diagnostics", "残差与误差结构诊断", "validation", ["预测模型需要检查偏差、异方差或自相关", "残差可按组/时间切片"], ["只看一个总体 RMSE", "把残差相关性当作可忽略噪声"], ["残差与预测值一一对应", "诊断图和阈值预先定义"], ["model", "result", "data_contract"], ["residual_report", "error_slices", "diagnostic_figures"], ["normality-agnostic-check", "autocorrelation", "heteroscedasticity"], ["bootstrap-uncertainty", "robust-regression"]),
    _method("conservation-invariant-check", "守恒量与不变量检查", "validation", ["机制模型有质量、能量、概率或库存守恒", "可计算闭合误差"], ["没有守恒定义仍套阈值", "误差抵消却不报告局部残差"], ["守恒量、边界通量和容差已定义", "数值误差与测量误差分开"], ["model", "result", "mechanism_contract"], ["conservation_report", "local_residuals", "violation_rate"], ["global-local-reconcile", "mesh-or-step-sweep", "unit-check"], ["dimensional-analysis", "mass-balance-compartment"]),
    _method("calibration-coverage-check", "概率校准与区间覆盖", "validation", ["输出概率、置信区间或预测区间", "决策依赖风险水平"], ["只报点预测不报覆盖", "在同一数据上反复调阈值"], ["置信水平和损失函数预先确定", "校准集与测试集隔离"], ["model", "result", "holdout"], ["calibration_report", "coverage_metrics", "reliability_curve"], ["calibration", "coverage-by-slice", "holdout"], ["bootstrap-uncertainty", "conformal-prediction"]),

    # Independent review cards: designed for a reviewer who did not author
    # the preceding route.
    _method("assumption-red-team", "假设红队审查", "review", ["模型链较长或依赖强假设", "需要逐条寻找失效情景"], ["由模型作者单独签字关闭风险", "把意见数量当作审查质量"], ["审查者拿到冻结输入和假设台账", "每个质疑有可复现实验或证据"], ["model_contract", "assumption_registry", "result"], ["critique_report", "assumption_status", "retest_requests"], ["independent-review", "assumption-perturbation", "owner-rebuttal"], ["counterexample-search", "scope-lock"]),
    _method("counterexample-search", "反例与边界搜索", "review", ["需要检验结论是否依赖特殊样本/参数", "可生成或枚举边界案例"], ["只挑有利反例", "未记录搜索域却宣称普遍失效"], ["反例生成规则透明", "成功/失败判据预先注册"], ["model", "result", "parameter_ranges", "constraints"], ["counterexample_set", "failure_modes", "boundary_map"], ["seed-replay", "minimal-counterexample", "out-of-domain-check"], ["assumption-red-team", "robustness-perturbation"]),
    _method("independent-reimplementation", "独立复算与重实现", "review", ["结果关键且需排除实现错误", "可获得输入、算法说明和固定种子"], ["复制作者代码后视作独立验证", "只比较最终数字不比中间量"], ["复算者与原实现上下文隔离", "环境、版本和命令可记录"], ["route_spec", "data_contract", "run_command", "result_hash"], ["reimplementation_report", "intermediate_checks", "reproducibility_status"], ["clean-run", "hash-reconcile", "tolerance-check"], ["manual-spot-check", "alternative-solver"]),

    # Writing cards: turn verified derivations and claims into a readable,
    # source-linked paper rather than a generic prose summary.
    _method("derivation-first-outline", "推导优先论文大纲", "writing", ["数学语言和逻辑链是主要评分对象", "需要逐问呈现定义—推导—结果"], ["先写结论再补公式", "用模型名替代变量、假设和接口"], ["题面覆盖和符号表已冻结", "每个结论有来源或计算证据"], ["subproblems", "variable_registry", "route_spec", "validation_report"], ["paper_outline", "derivation_map", "section_claims"], ["question-coverage", "claim-evidence-link", "notation-check"], ["claim-evidence-index", "manual-outline-review"]),
    _method("claim-evidence-index", "结论—证据索引", "writing", ["论文包含多个数值、图表和政策结论", "需要区分 observed/derived/hypothesis"], ["无证据数字直接入稿", "把候选资料引用写成验证事实"], ["每个 claim 绑定 revision、范围和证据", "未验证项保留状态标签"], ["paper_claims", "evidence_refs", "validation_report"], ["claim_index", "provenance_table", "unverified_items"], ["reference-resolve", "claim-status-audit", "hash-check"], ["derivation-first-outline", "manual-citation-review"]),
    _method("three-line-table-layout", "三线表与公式排版", "writing", ["需要清晰呈现变量、参数、结果和对比", "目标格式支持 LaTeX/Word 三线表"], ["把装饰图当作数学证据", "表格缺单位、分母或样本范围"], ["表题、单位、脚注和来源齐全", "公式编号与正文引用一致"], ["variable_registry", "result", "claim_index"], ["typeset_tables", "equation_refs", "figure_manifest"], ["rendered-page-review", "table-unit-check", "cross-reference-check"], ["plain-markdown-table", "manual-format-review"]),

    # Defense cards: rehearse evidence-backed answers and disclose boundaries.
    _method("defense-question-matrix", "答辩问题矩阵", "defense", ["需要预演方法选择、假设、验证和局限追问", "队员分工明确"], ["背诵与论文无证据的口号", "把评委可能问题当作已知事实"], ["问题来自题面和审查记录", "每个回答绑定证据或明确未知"], ["paper_draft", "critique_report", "validation_report"], ["question_matrix", "answer_cards", "owner_assignments"], ["coverage-by-subproblem", "timed-rehearsal", "evidence-link-check"], ["risk-first-answer", "manual-mock-defense"]),
    _method("evidence-ledger-rehearsal", "证据账本演练", "defense", ["评委可能追问数据来源、参数和数字复现", "已有 artifact/run/hash 台账"], ["现场临时编造来源或参数", "用截图替代可复现命令"], ["账本与目标 revision 一致", "敏感资料按权限脱敏"], ["claim_index", "evidence_refs", "run_manifest"], ["defense_evidence_pack", "source_map", "reproduction_commands"], ["hash-reconcile", "clean-run", "access-check"], ["printed-source-index", "owner-escalation"]),
    _method("risk-first-answer", "风险优先答辩脚本", "defense", ["模型有明显外推、参数或数据限制", "需要在有限时间内诚实解释边界"], ["回避失败案例", "把 hypothesis 说成 verified"], ["风险登记和 fallback 已批准", "回答区分观察、推导与假设"], ["paper_draft", "assumption_registry", "critique_report", "validation_report"], ["risk_script", "fallback_explanations", "limitation_summary"], ["timed-rehearsal", "claim-class-audit", "counterexample-recall"], ["defense-question-matrix", "manual-owner-review"]),
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
    "METHOD_FAMILY_BLOCK_KINDS",
    "REQUIRED_BLOCK_IDS",
    "BUILTIN_METHODS", "BUILTIN_BLOCKS", "BUILTIN_PRESETS", "BUILTIN_ARCHETYPES", "BUILTIN_CONTENT_PACKS",
    "metadata_snapshot_to_catalog", "build_capability_catalog", "validate_composition", "validate_workflow", "compose_workflow", "composition_diff",
]
