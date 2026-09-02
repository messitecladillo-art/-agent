---
name: workflows-cumcm-main
description: 使用固定的高教社杯国赛主流程从题面锁定到论文发布；适用于比赛日或完整演练，保留必要硬门并允许在题型块中替换方法。
---

# 固定方案：高教社杯国赛主流程

这是可直接执行的默认 DAG，不是把每道题套成同一模型。先读当届官方通知，再根据
题型插入机制、优化、预测或仿真块。

## 主链

scope-lock
→ question-decomposition
→ data-and-evidence
→ model-routing
→ mathematical-derivation
→ solver-reproducibility
→ validation-and-adversarial-review
→ paper-and-typesetting
→ defense-and-release

## 时间盒（可调整，必须记录）

- 0–2 h：题面、附件、题型和小问 DAG；
- 2–10 h：数据/变量/假设/主备路线；
- 10–40 h：baseline 与 primary 求解；
- 40–52 h：验证、敏感性、红队；
- 52–64 h：论文、图表、附录；
- 最后 6–8 h：冻结模型、终检、渲染和提交包。

时间不是硬规则；实际截止时间来自当届通知。超时必须触发 fallback 或 Owner 决策。

## 每阶段出口

| 阶段 | 产出 | 进入下一阶段的门 |
|---|---|---|
| scope | problem-contract | 版本/题号/附件/profile 冻结 |
| questions | coverage matrix/DAG | 每小问有目标、输出和约束 |
| data | data-contract | 字段/单位/缺失/切分/泄漏可审 |
| route | model-contract | baseline、主备、适用域和验证计划 |
| derivation | equation/assumption registry | 定义、量纲、边界和接口完整 |
| solver | run-manifest/results | 干净运行、命令、种子、hash |
| validation | validation/review report | 互补证据、关键 finding 关闭 |
| paper | PDF/DOCX/claim/crossref | 数字一致、渲染和引用通过 |
| release | evidence/defense pack | Owner 批准且可回滚 |

任何“跳过”必须写 skip_reason、替代证据和风险，不得静默跳门。

## 群聊式角色编排

固定流程的“群聊”是状态同步界面，不是多人同时自由发言。每个阶段只允许一个
primary owner 写主工件，其他成员以独立意见或 review 事件进入群聊；Coordinator
只负责排序、冻结 revision 和转发，不替作者关闭审查门。默认的角色—写集如下：

| 角色 | 主要阶段 | 允许写入 | 不允许做的事 |
|---|---|---|---|
| Scope Sentinel | scope/questions | `artifacts/scope/`、问题覆盖表 | 选主模型、修改原始题面 |
| Data/Domain Steward | data/contract | `data/processed/`、数据契约、参数台账 | 覆盖 raw、把相关当因果 |
| Route Strategist | route/derivation | `artifacts/routes/`、方程/假设登记 | 直接改写别人的路线结论 |
| Solver | computation | `models/`、`artifacts/runs/`、日志 | 无契约运行、只报最终数字 |
| Critic/Challenger | review | `artifacts/validation/`、findings | 审查自己的 P0/P1 并自行关闭 |
| Paper Steward | paper/defense | `paper/`、claim/图表索引 | 写入未 VERIFIED 数字 |
| Release Auditor | release | `artifacts/release/`、审计报告 | 未获 Owner 批准执行提交 |

### 每次交接的最小消息

群聊消息必须是可定位工件的摘要，正文至少包含：`sender`、`receiver`、协议版本、
nonce/idempotency key、`input_revision`、`target_revision`、数据分类、状态、
claim_class、证据引用、命令/退出码、未决项、风险和下一动作。长推导、表格和日志
写入版本化文件，消息只放摘要和链接，避免聊天成为第二套事实源。

### 比赛日降级与恢复

当某一阶段超过时间盒、求解器不收敛或外部 Agent 不可用时，按以下顺序降级：

1. 保留当前 revision 和失败日志，先停止无界重试；
2. 回到透明 baseline 或已验证 fallback，写明损失与适用边界；
3. 若 baseline 也无法回答题面，标 `BLOCKED` 并由 Owner 决定是否缩小问题；
4. 恢复后必须产生新 revision，不能把旧失败结果原地改成成功；
5. 外部 Agent 未连接时仅生成 `PENDING_RELAY`，不把“已派发”写成“已完成”。

## 固定流程的最终冻结清单

在 `defense-and-release` 前，Coordinator 逐项核对：

- 每个小问至少有一条题面原句、一个可交付输出、一个 baseline 和一个验证记录；
- 每个关键数字可由 `claim → artifact → run_manifest → input/code revision` 回放；
- 主模型相对 baseline 的差异有消融、对照或边界实验，不以模型数量充当创新；
- 论文中的公式、符号、表图、代码和摘要数字来自同一冻结 revision；
- 所有跳过项、低置信度来源、未决参数和不能推广的结论均在限制中披露；
- release pack 包含清单、哈希、命令、环境、审查结果、回滚指针和 Owner 审批。

任何一项不满足都只能输出 `READY_FOR_REVIEW` 或 `BLOCKED`，不能输出“基本完成”。
