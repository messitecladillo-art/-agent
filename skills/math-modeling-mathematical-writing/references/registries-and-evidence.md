# 注册表与证据账本

这些结构用于让写作代理、求解代理、评审代理和 Owner 共享同一事实来源。字段可扩展，
但不要删除能回放来源、范围和限制的字段。所有注册表必须声明同一个 `input_revision`；
版本不一致时旧结果只能只读引用，不能静默进入当前论文。

## 1. 通用状态与主张类别

```text
OBSERVED          来源中直接可定位
INFERRED          根据 OBSERVED 推导出的建议
HYPOTHESIS        尚未验证的假设/预期
OFFICIAL_PENDING  官方规则尚未锁定
CANDIDATE         候选方法或参数，未获当前题目证据支持
VERIFIED          通过指定验证且可回放
UNVERIFIED        有输出但缺关键验证/来源
BLOCKED           存在阻塞错误，不得进入发布
```

`claim_class` 和 `status` 不互相替代：一个 `INFERRED` 的写作建议可以是 VERIFIED（规则
已被团队接受），而一个当前题目的数字即使来自脚本，也要在独立验证后才能标 VERIFIED。

## 2. problem_contract

```yaml
schema: problem-contract/v1
input_revision: git:<commit-or-manifest-sha>
contest: <竞赛名称>
edition: <届次/版本>
group: <组别>
problem_id: <题号>
official_format:
  source_ref: <官方文件/页码>
  status: VERIFIED | OFFICIAL_PENDING
subproblems:
  - id: Q1
    prompt_ref: <题面页码/段落>
    objective: <要回答的关系、预测、决策或证明>
    deliverables: [<数值/表/图/方案>]
    constraints: [<范围/格式/资源约束>]
    expected_evidence: [<验证类型>]
```

题面没有明确编号时可以先生成 `Q1-draft`，但必须标记草稿，不得据此宣称已覆盖所有小问。

## 3. variable_registry 与 assumption_registry

```yaml
schema: variable-registry/v1
input_revision: git:<same-revision>
variables:
  - id: state:inventory
    symbol: I_t
    meaning: <含义>
    kind: state
    unit: kg
    domain: "t ∈ {0,...,T}"
    granularity: item-time
    sign_convention: nonnegative
    source_ref: data:inventory-column
    status: VERIFIED
```

```yaml
schema: assumption-registry/v1
input_revision: git:<same-revision>
assumptions:
  - id: asm:stationary-rate
    statement: <在明确范围内的可检验假设>
    reason: <为何需要>
    applies_to: [Q1, eq:q1-balance]
    test: <残差/敏感性/边界案例/外部数据>
    disable_when: <失效条件>
    relaxation: <备用模型>
    status: HYPOTHESIS
```

结果/派生量若不是可登记的变量，也要有稳定 ID，供公式输出和 claim 回链：

```yaml
results:
  - id: result:q1-estimate
    meaning: <由模型或验证产生的结果>
    unit: <单位或无量纲>
    artifact_refs: [artifacts/q1/result.csv]
    status: VERIFIED
```

## 4. equation_registry

```yaml
schema: equation-registry/v1
input_revision: git:<same-revision>
equations:
  - id: eq:q1-balance
    label: eq:q1-balance
    question_id: Q1
    role: definition | objective | constraint | governing | discretization | criterion
    inputs: [state:inventory, param:rate]
    outputs: [state:inventory-next]
    domain: "t=0,...,T-1"
    assumptions: [asm:stationary-rate]
    derivation_from: [def:flow]
    unit_check:
      status: VERIFIED
      terms: ["kg/day", "kg/day"]
    approximation: none
    validation_refs: [val:q1-conservation]
    source_ref: paper/main.tex:120
    status: VERIFIED
```

规则：`id`/`label` 唯一；输入和输出必须在变量或结果注册表中存在；核心公式必须有
`question_id`、适用域、前置假设和验证引用。`unit_check.status != VERIFIED` 时不能把
依赖它的 claim 升级为 VERIFIED。若公式组包含初值、边界或接口，分别登记其角色，不要
把条件藏在图片或脚注里。

## 5. crossref_manifest

推荐使用 JSON（便于脚本和前端读取），YAML 也可：

```json
{
  "schema": "crossref-manifest/v1",
  "input_revision": "git:<same-revision>",
  "items": [
    {
      "id": "fig:q1-error",
      "kind": "figure",
      "label": "fig:q1-error",
      "caption": "误差随时间的变化及适用范围",
      "cited_by": ["claim:q1-stability"],
      "source_artifact": "artifacts/q1/error.svg",
      "generator": "scripts/plot_q1.py",
      "unit": "h",
      "status": "VERIFIED"
    }
  ]
}
```

每个 item 的 `label` 唯一，`caption` 不能是空泛的“结果图”，`cited_by` 至少包含一个
正文位置或 claim，`source_artifact` 和 `generator` 必须能回放。表格的 caption 在表上、
图的 caption 在图下是常见约定，但最终位置由官方模板字段决定。

## 6. claim_matrix

```yaml
schema: claim-matrix/v1
input_revision: git:<same-revision>
claims:
  - id: claim:q1-stability
    question_id: Q1
    text: <不超过一两句的可检验主张>
    value: <数值/区间/方向，可为空>
    scope: <数据集、时间窗、情景、分母>
    evidence_refs: [result:q1-table, val:q1-holdout]
    command: "python scripts/run_q1.py --config configs/q1.json"
    exit_code: 0
    artifact_hash: sha256:<64hex>
    validation_refs: [val:q1-holdout, val:q1-sensitivity]
    limitations: [<不能推出的结论>]
    claim_class: OBSERVED
    status: VERIFIED
```

数字若没有 `scope`、分母、来源、命令或验证，状态必须为 `UNVERIFIED`。摘要、正文、
表格和图中的同一数字应引用同一个 claim，而不是手工复制四份。

## 7. validation_results 与 artifact_manifest

```yaml
schema: validation-results/v1
input_revision: git:<same-revision>
checks:
  - id: val:q1-holdout
    kind: holdout | cross-validation | feasibility | conservation | convergence | sensitivity | render
    scope: <数据/参数/网格/页码范围>
    threshold: <预先规定的容差或通过条件>
    command: <可复现命令>
    exit_code: 0
    result_hash: sha256:<64hex>
    findings: []
    status: VERIFIED
```

```yaml
schema: artifact-manifest/v1
input_revision: git:<same-revision>
artifacts:
  - path: artifacts/q1/error.svg
    kind: figure
    sha256: sha256:<64hex>
    generated_by: scripts/plot_q1.py
    dependencies: [data:q1.csv, env:requirements.lock]
    status: VERIFIED
```

## 8. 复核报告最小格式

```yaml
schema: paper-review/v1
input_revision: git:<same-revision>
reviewer: <独立代理或 Owner>
findings:
  - id: P1-EQ-001
    severity: P0 | P1 | P2 | note
    location: <文件:行/页码/label>
    observation: <看到的事实>
    impact: <对正确性、复现或版式的影响>
    recommendation: <最小修复>
    status: open | fixed | accepted-risk
verdict: BLOCKED | READY_FOR_REVIEW | RELEASED
```

评审者只写发现和证据，不直接替作者掩盖问题；修复后要以新的 `input_revision` 重跑。

## 9. 典型阻塞条件

- 子问题没有对应 claim 或交付物；
- 符号首次使用前未定义、同符号换义、单位/粒度不明；
- 公式 label 重复、交叉引用不存在、手写编号漂移；
- 加法项/目标/约束量纲不一致，或秒/小时等换算未记录；
- 只有训练集指标、单次仿真或单个最优值，没有互补验证；
- 数字无法从结果文件和命令回放，随机过程无种子；
- 图表无单位/图例/生成脚本，表题或图题位置违反锁定的官方格式；
- 范文原文、原图、原代码、个人信息或未授权材料被直接复制；
- PDF/Word 渲染有缺字、公式/代码裁切、浮动体遮挡或显著空白。
