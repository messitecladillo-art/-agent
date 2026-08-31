# MVP QA 记录

测试日期：2026-08-31（Asia/Shanghai）

## 自动/静态检查

- `node --check app.js`：通过。
- `python -m py_compile backend/app.py`：通过。
- `python -m pytest backend -q`：54 passed（能力别名与模型路由预览、数据策略 allow-list、adapter 异常 fallback、预算/延迟/风险审批门、API 幂等/CAS、写集/DAG、租约 reclaim/fencing、结果回执、发现项门禁、relay ACK、事件 hash chain、可选 journal、统一 run identity/context、消息 modeling provenance、双验证族与 legacy 结果阻断）。
- 本地 FastAPI `/health`：`ok=true`。
- Snapshot：返回统一项目/运行身份、完整 SHA-256 revision、`context.input/worktree/control_revision`、任务/消息/审批/relay/finding 投影、`event_chain_valid` 和 `antigravity=PENDING_RELAY`。
- Snapshot：额外返回 `modeling.source_status=unavailable`（本地服务没有真实题面契约）和 `release_gate`；客户端因此不会把静态 Q 骨架当成 live 题面。
- 幂等性：同一个 `idempotency_key` 两次 POST 返回相同 event id 且不重复写消息；不同请求复用 key 返回 `IDEMPOTENCY_CONFLICT`。
- 版本门禁：使用旧 `base_revision` 的 POST 返回 HTTP 409。
- 租约门禁：活跃 lease 拒绝其他 Agent 抢占，过期 lease 可被更高 fencing epoch reclaim，旧 epoch 的 heartbeat/result/handoff 返回 409；结果回执会关闭 worker lease。
- 质疑门禁：开放 P1 finding 时禁止 accept；关闭 finding 后才可进入 VERIFIED。
- 数学验证门：显式建模结果缺 `problem_type`、两种不同 `check_kind`、scope/threshold、`exit_code=0` 或 SHA-256 时返回 `VALIDATION_STRUCTURE_INVALID`；旧结果只能保持 `UNVERIFIED`。
- provenance/release 门：结果文件没有 manifest linkage 时不能 accept；`release_gate` 还要求所有任务完成并有 Owner release approval。
- 外部边界：未有已记录 Owner approval 的外部 relay 返回 428；relay 仍保持 `PENDING_RELAY`，只有 nonce/input hash 匹配的 ACK 才会变为 `CONNECTIVITY_VERIFIED`。
- 事件完整性：每个事件带 `prev_hash/event_hash`，启动时校验日志链；这只保护事件日志，不替代生产数据库与身份鉴权。
- 可选 journal：`COLLAB_STATE_FILE` 的原子 JSON journal 可在重启后恢复事件和控制面投影；多进程仍未承诺。
- Skill 验证：`quick_validate.py` 输出 `Skill is valid!`。

## 浏览器交互检查

- 桌面宽度：三栏布局、频道、群聊、DAG、证据账本和审批门均可见。
- 手机宽度 390×844：左栏折叠，建模概览、当前小问、验证门与审批入口仍可访问；无水平溢出。
- 频道切换：标题、副标题和活动状态更新。
- 发送消息：Owner 消息进入时间线，模拟模式返回 Agent 回执。
- Live 模式：`http://127.0.0.1:8787/?live=1` 能取得 snapshot，并通过 WebSocket 接收事件。
- Live 断线：按 `seq` 回放事件；REST replay 与 WebSocket 交错时不会回退 CAS revision；坏 JSON 事件会被忽略并提示。
- Live 写入失败：不生成模拟 Agent 回执，Owner 消息标记 `LOCAL_PENDING`；`STALE_REVISION` 会刷新快照并要求确认后重发。
- Live snapshot：任务状态会同步到右侧任务列表，事件类型和实际 actor 映射到群聊投影。
- 建模优先首屏：Q1—Q4 覆盖卡、题面→论文链、路线 A/B 必填字段、题型验证与发布门矩阵均可见；点击 Q3 与完整链弹窗可核对字段。
- provenance：群聊消息显示 `SIMULATED/LIVE` 来源、`observed/derived/hypothesis`、task/Q、target revision、状态和 evidence refs；证据预览对 fixture 只显示 `PRODUCED/UNVERIFIED/BLOCKED`，不伪造 `VERIFIED`。
- fail-closed：缺少 provenance 的消息显示 `unknown/UNVERIFIED` 和 `evidence: none`；live 快照缺题面时 Q 卡自动 `BLOCKED`，不复用 fixture prompt。
- 范文依据弹窗：可查看 2016—2025、13 条公开样本的观察模式、挑战结论和样本限制，并链接官方展示/评审入口。
- Agent/任务/证据点击：均打开只读详情弹窗。
- 审批按钮：只改变本地 UI 标记并提示，不执行外部发布。
- 暂停按钮：在暂停与恢复之间切换，并显示提示。
- `prefers-reduced-motion`：CSS 提供降级规则。
- 浏览器控制台：无 error/warn。

## 仍需在生产版补测

- OIDC/RBAC、真正的多进程事务/签名 relay、真实 connector、secret 扫描和敏感数据传输审批。
- 多进程事件原子追加、lease fencing、Postgres/WAL 故障恢复。
- 大文件/归档炸弹/symlink 逃逸和模型 prompt injection 测试。
- 往届题隔离回放、数学结果独立复核、论文 PDF 视觉 QA 和竞赛提交包检查。
