# Modeling-first 工作台设计

## 一句话原则

群聊负责让协作可见，建模链负责让结果可检查，证据账本负责让结论可追溯，评审门负责让未验证内容不能伪装成论文结论。

## 首屏应回答的八个问题

1. 当前锁定的是哪一届、哪一组、哪一道题、哪一个输入 revision？
2. 题目有几个小问，每个小问的交付物和硬约束是什么？
3. 当前聚焦的小问有哪些变量、单位、观测量和参数来源？
4. 哪些内容是事实，哪些是推导，哪些仍是假设？
5. 主路线、baseline 和 fallback 的接口是否对齐？
6. 当前验证是否与题型匹配，是否有两个互补检查和 clean-run？
7. 哪些数字/规则可以进入论文 claim，哪些仍是 `PRODUCED` 或 `UNVERIFIED`？
8. 最大阻断是什么，Owner 下一步要批准什么？

## 信息架构

### A. 运行上下文条

统一显示：

```yaml
project_id: HGC-MF-2026-001
run_id: RUN-MF-2026-0831
mode: simulated|live
source_status: fixture|local_event_store|stale|blocked
input_revision: manifest:<64 hex>
worktree_revision: manifest:<64 hex>
control_revision: manifest:<64 hex>
```

任何消息、任务或证据详情都从同一个 `runtime_context` 继承这些字段。真实运行时三种 revision 必须是服务端签发的 `manifest:<64 hex>`；静态演示可以使用带 `fixture:` 前缀的可读 ID，但必须同时显示 `SIMULATED · fixture`，不能把它当成题面或代码的完整性证明。没有 artifact manifest 时，状态只能是 `UNVERIFIED`、`PRODUCED` 或 `BLOCKED`。

### B. Q 覆盖条

每个小问由一个 `subproblem` 实体表示：

```yaml
id: Q2
prompt_refs:
  - artifact_id: problem.pdf
    page: 2
    quote: "..."
deliverables: [变量/单位/假设登记, route_spec]
variables: [x, theta, y]
assumption_ids: [A-02, A-03]
route_ids: [route-A, route-B]
validation_ids: [V-02, V-03]
claim_ids: [C-Q2-01]
shared_artifact_ids: [clean-data-v1]
source_status: verified|image_only|unavailable
```

`prompt_refs` 缺失或来源为 `image_only/unavailable` 时，Q 不得显示为完成；可继续讨论，但必须留在 `BLOCKED/UNVERIFIED`。

### C. 模型链

模型链不是“算法名列表”，而是带接口的有向图：

```text
题面句 → 小问交付物 → 变量/单位/粒度 → 假设/适用域
      → baseline → primary/fallback → 算法入口/容差
      → 结果表/图 → 题型验证 → paper claim → release gate
```

每条边至少带：`from`、`to`、符号/字段、单位、时间/空间粒度、provenance、禁用条件和 target revision。共享清洗或验证脚本只运行一次，通过 `shared_artifact_ids` 映射到多个 Q，不能重复计数。

前端演示也会把变量登记与链边作为独立实体渲染；真实 API 应提交同样的结构，而不是把单位、粒度和来源塞进一段不可解析的说明文字。

### D. 群聊投影

每条关键消息固定显示：

```yaml
source: fixture|snapshot|live|local_pending
status: PRODUCED|READY_FOR_REVIEW|VERIFIED|ACCEPTED|RELEASED|UNVERIFIED|BLOCKED
claim_class: observed|derived|hypothesis|unknown
task_id: G5
subproblem_id: Q2
model_profile: provider/model/version
target_revision: manifest:<64 hex>
evidence_refs: [artifact:..., run:..., claim:...]
event_seq: 42
event_hash: sha256:...
```

缺字段不是空白，而是显式 `unknown/unverified`。颜色只做状态提示，不代表真伪。

## 题型验证矩阵

| 题型 | 必须覆盖的互补检查（至少两类） | 常见误读 |
|---|---|---|
| 预测/统计 | 隔离切分、回测/CV、残差/不确定性、基线比较 | 把 R² 当成策略保证 |
| 优化/运筹 | 可行性、约束违反率、上下界/最优性 gap、敏感性/鲁棒性 | 只报一个最优值 |
| 仿真/物理 | 量纲、守恒、边界/初值、时间步/网格收敛、稳定性 | 只跑一次仿真 |
| 机制/政策 | 识别性、情景扰动、外推禁用条件、专家合理性 | 把相关性写成因果 |

每项检查都要有命令、退出码、结果 hash 和适用范围。验证状态 `PRODUCED` 不得直接升级为 `VERIFIED`。

本地 API 对显式建模回执执行 fail-closed 校验：`problem_type`、至少两个不同
`check_kind`、`scope`、`threshold`、`exit_code=0` 和 `sha256` 均为必需字段；
`artifact_manifest` 与 `paper_claims` 还必须在 accept/release 前通过
`provenance_gate`。没有真实题面契约的 live snapshot 会返回
`modeling.source_status=unavailable`，客户端将 Q 保持为 `BLOCKED`。

## 论文与发布门

建议使用 T03 的 7 维 rubric（100 权重、0—3 分）：题面覆盖 20、数学化/量纲 20、假设/适用域 15、路线/算法 15、验证 15、论文 claim 可追溯 10、发布门 5。它是决策支持，不是模型投票。

- `candidate_route`：硬门均至少 2 分，P0/P1 为 0。
- `paper_numeric_claim`：R1—R6 至少 2 分，且 provenance 为 `VERIFIED/ACCEPTED`。
- `release`：所有维度至少 2 分、clean snapshot 可复现、Owner approval 与 target revision 相符。

开放 P0/P1、缺 hash、来源未获取、奖项状态仅来自文件名/二次仓库，都会阻断 `ACCEPTED/RELEASED`。

## 群主交互原则

- 群主可以锁定题面、选择/拒绝路线、批准参数范围、批准外部 relay、接受明确风险和发布。
- Agent 可以提出、复算、质疑和请求复跑，但不能修改其他 Agent 的写集、改变验收条件或自行把红灯改绿。
- 未接入真实 API 的按钮必须写 `DEMO_ONLY`；刷新后状态以 snapshot/event 重建，不以 DOM 的透明度为事实。
