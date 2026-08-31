# G-CUP MAS 详细架构

## 0. 设计目标

G-CUP MAS（高教社杯 Mathematical Agent System）服务于一支真实参赛队，而不是展示“模型会聊天”的玩具。系统必须同时满足：

1. **群聊可理解**：人可以像管理一个研究群一样看见谁在说话、谁在等待、谁被阻塞、谁需要审批。
2. **任务可执行**：每个 Agent 有明确输入、输出、写集、预算、截止时间和验收测试。
3. **结论可追溯**：每个关键数字/公式/规则事实都能回到来源、运行命令、版本和证据。
4. **意见可反驳**：独立方案先互盲产生，再由 Critic/Challenger 证据化攻击；分歧保留，不用多数票掩盖。
5. **结果可复现**：从冻结快照在干净环境重跑，才允许进入论文和发布包。
6. **群主有最终控制权**：用户是唯一 Owner，Agent 的评分、投票和建议都不能替代人的批准。

## 1. 总体拓扑

本版本的建模优先字段和验收依据见 [`modeling-first-workbench.md`](modeling-first-workbench.md)；近十年公开范文的样本边界与结构证据见 [`exemplar-study-2016-2025.md`](exemplar-study-2016-2025.md)；Owner 的冲突裁决见 [`../.collab/decisions/adjudication-2016-2025.md`](../.collab/decisions/adjudication-2016-2025.md)。它们是设计证据，不是对任何具体论文奖项或模型正确性的替代判断。

```text
┌──────────────────────────────────────────────────────────────┐
│                         Owner Console                        │
│  你：锁题/审批/暂停/重派/质疑/接受风险/最终发布               │
└─────────────────────────────┬────────────────────────────────┘
                              │ WebSocket/SSE projection
┌─────────────────────────────▼────────────────────────────────┐
│                         Web App (群聊前端)                    │
│ ChannelSidebar │ GroupChat │ AgentRoster │ DAG │ Evidence    │
│ ReviewPanel    │ ApprovalModal │ AuditTimeline               │
└─────────────────────────────┬────────────────────────────────┘
                              │ REST + event cursor
┌─────────────────────────────▼────────────────────────────────┐
│                      Orchestrator / Coordinator               │
│ Dispatch Gate │ DAG Scheduler │ Lease/CAS │ Budget │ Gate     │
│ Context Curator │ Conflict Adjudicator │ Model Router         │
└───────────────┬──────────────────┬───────────────────────────┘
                │                  │
     ┌──────────▼─────────┐  ┌─────▼─────────────────────────┐
     │ Model Gateway       │  │ Durable Control + Evidence    │
     │ OpenAI/Codex        │  │ Postgres/SQLite                │
     │ Claude              │  │ Object store / .collab         │
     │ Qoder               │  │ events + manifests + reviews   │
     │ Antigravity         │  └────────────────────────────────┘
     │ other providers     │
     └──────────┬─────────┘
                │ structured task/result envelopes
     ┌──────────▼─────────┐
     │ Sandboxed Tool Run  │
     │ Python / LaTeX /    │
     │ OCR / solver / test │
     └─────────────────────┘
```

前端绝不直接调用模型。所有 Agent 行为都经过 Orchestrator，所有状态变更都先写事件，再投影到聊天界面。聊天是“可读视图”，不是数据库。

## 2. 运行模式

### SOLO

适用于翻译、一句话润色、单文件格式化、确定性检查等低风险强顺序任务。无 Agent fan-out、无外部调用、无 `.collab/` 初始化。

### LITE

适用于一个明确产出但需要第二视角的任务：一个 Worker 产出，一个独立 Critic 只读复核，最多一轮修复。

### FULL

适用于完整数学建模、研究+代码+论文、多方案路线、高不确定性、敏感数据或用户明确要求跨厂商审查的任务。至少包含两条独立路线、Critic/Challenger、Validation 和 Release 门。

FULL 启动前必须在 charter 中写明：`max_agents`、`max_parallel`、`max_depth`、预算、截止时间、数据级别、外部传输授权、停止条件。默认 `max_depth=1`，子 Agent 不得自行再派生 Coordinator。

## 3. 竞赛生命周期

### 3.1 赛前校准

- 收集 3–5 道往届题作为 `golden_tasks`，题面、参考答案和隐藏标签隔离。
- 对候选模型测题面覆盖、变量/单位准确率、代码复现、反例命中率、中文写作和延迟/成本。
- 记录模型版本、提示版本、工具权限和数据驻留策略。
- 准备 PDF/Excel/OCR/LaTeX/优化器的 smoke test 与离线依赖锁定。

### 3.2 T0 读题与规则锁定

Rule/Integrity Officer 和 Scope-Lock 串行完成：

- 锁定届次、组别、题号、赛区、阶段、截止时间和官方文件版本。
- 逐句把题面映射到小问、变量、单位、约束、评价指标和交付物。
- 为原始题面和附件生成 SHA-256；未获取的条款写 `UNAVAILABLE/待确认`，不从往届经验补全。
- 发现缺件、版本冲突或规则歧义时进入 `BLOCKED`，由 Owner 决定是否继续。

### 3.3 数据/机制理解

Data Auditor、Vision/OCR、Domain Specialist 并行，但只读冻结原始快照：

- 数据：编码、表头、行列数、缺失、重复、异常、泄漏、抽样、时间/空间粒度。
- 机制：因果图、守恒关系、边界/初始条件、参数可识别性和适用域。
- 抽取：扫描图表/公式回写到可引用文本与结构化表，不把 OCR 猜测当原文。

### 3.4 路线争论

Model-A、Model-B（必要时 Model-C）接收同一个 G5 冻结快照，但互相不可见。每条路线必须给出：

```text
问题适配 → 变量/状态/参数 → 假设 → 目标函数/评价指标
→ 约束/边界 → 算法与复杂度 → 参数来源
→ 验证设计 → 失败模式 → 回退路线 → 论文接口
```

Critic 按 rubric 评分并写 finding；作者逐条 rebuttal；Coordinator 不代替 Critic 改理由；Owner 选择、拒绝或批准融合接口。

### 3.5 实现与集成

数据管线、基线、分问 Solver、优化/仿真可并行，前提是 write_set 不重叠且公共 schema/单位已锁定。所有结果表由脚本生成，不接受手改数字。Coordinator 在集成前冻结 revision，统一参数、随机种子、容差、图表和跨小问接口。

### 3.6 验证与挑战

Validation Auditor 从干净快照复算，不读取作者解释；根据题型选择：

- 预测/统计：时间或分组隔离、回测/CV/留出、残差、不确定性、误差传播。
- 优化：可行性、约束违反率、上下界、最优性 gap、敏感性和鲁棒性。
- 仿真/物理：量纲、守恒、边界、初值、时间步/网格收敛、稳定性。
- 机制/政策：因果识别、情景扰动、外推禁用条件、专家合理性。

Challenger 主动找漏题、反例、数据泄漏、过拟合、外推和模型—图表—文字矛盾。P0/P1 未闭合时红灯不可由 Agent 自行关闭。

### 3.7 论文与发布

Paper/Judge Advocate 只能读 `VERIFIED` 或 `ACCEPTED` claim。Release Auditor 在干净环境重跑并检查：源码、数据、图表、论文、引用、匿名、文件名、页数、依赖、随机种子、哈希和压缩包结构。Owner 写入 `approval_id` 后才进入 `RELEASED`。

## 4. 上下文同步

不要把完整群聊塞给每个 Agent。Coordinator 为每个任务生成最小 `context_packet`：

```yaml
problem_contract: .collab/artifacts/scope/problem_contract.yaml
data_summary: .collab/artifacts/data/summary.md
assumption_registry: .collab/artifacts/domain/assumptions.yaml
claim_index: .collab/claim_index.yaml
relevant_artifacts: [A-12, A-19]
input_revision: manifest:...
禁止事项: ["不得修改 raw", "不得读 route_A"]
acceptance: ["..."]
```

Agent 只回传 delta：新增 claim、evidence、风险、测试和下一步。Context Curator 定期生成 checkpoint，并保留原件引用；摘要不能覆盖原始证据。路线候选互盲，Critic 不读作者自述，Validation 不读解释，Paper 不读未验收草稿。

## 5. 状态与并发

任务状态：

```text
QUEUED → CLAIMED → IN_PROGRESS → READY_FOR_REVIEW
       → VERIFIED → INTEGRATED → ACCEPTED → RELEASED
```

可终止/旁路：`FAILED`、`TIMEOUT`、`BLOCKED`、`CANCELLED`、`SUPERSEDED`。`PRODUCED` 只是工件状态，不代表任务验收。

- Git 项目：用 commit/tree SHA，Worker 使用独立 branch/worktree。
- 非 Git 项目：用规范化排序文件清单 + SHA-256，排除 `.collab/` 控制事件。
- `input_revision`、`worktree_revision`、`control_revision` 分开；追加事件不会让所有结果失效。
- 同一 base 上只有不相交的规范化 write_set 才能三方合并；合并后必须重跑受影响检查和全量回归。
- lease 包含 TTL、heartbeat、fencing epoch；过期 session 只能读，不能覆盖新结果。
- 每个事件有 `event_id/seq/prev_hash/actor/time/type`，原子追加，禁止重写历史。
- 本地 journal 启动时会校验 `prev_hash → event_hash` 链并在篡改时拒绝启动；该链只证明事件日志连续性，不证明投影文件、模型输出或调用者身份未被伪造，生产版仍需数据库事务、签名 relay 和 OIDC/RBAC。

## 6. 评分与门禁

路线评分是决策支持，不是投票替代：

```text
route_score = Σ(weight_i × score_i) − penalty
```

建议维度：问题适配 0.16、数学正确性 0.16、数据验证 0.14、可实现性 0.12、优化质量 0.10、原创性 0.08、可解释性 0.08、鲁棒性 0.08、论文表达 0.08。路线默认总分 ≥7.0 且前三项各 ≥6；最终发布建议 ≥8.0、P0=0、P1=0、关键 claim 证据覆盖 100%、clean-run 100%。

## 7. 故障策略

| 故障 | 系统动作 |
|---|---|
| 模型 API 失败 | 同能力重试一次 → fallback → `MODEL_UNAVAILABLE`；不把失败当完成 |
| Agent 超时/崩溃 | lease 过期、旧 session 只读、保留旧证据、提高 fencing epoch 后 reclaim 或按幂等键重派 |
| 前端断线 | 本地/服务端继续 append event；恢复后按 `after_seq` 补发 |
| 版本冲突 | 拒绝写入，提示 rebase；不覆盖他人结果 |
| 外部 Agent 不可用 | 生成 `PENDING_RELAY`，显示待转交，不声称实时同步 |
| 预算超限 | 压缩上下文 → 换同能力低成本模型 → 减少非关键并发；不跳过 Critic/Release/关键测试 |
| 规则/题面缺失 | `BLOCKED`，请求 Owner 补件或明确风险批准 |
