# API 与事件契约（agent-collab/v1）

## 1. 事件统一格式

```json
{
  "protocol": "agent-collab/v1",
  "project_id": "HGC-MF-2026-001",
  "run_id": "RUN-MF-2026-0831",
  "event_id": "evt-00042",
  "seq": 42,
  "timestamp": "2026-08-31T14:32:00Z",
  "actor_id": "critic/session-abc",
  "type": "CRITIQUE",
  "channel": "validation",
  "task_id": "G7",
  "base_revision": "manifest:<64 hex>",
  "payload": {},
  "idempotency_key": "G7/critic/session-abc/attempt-1",
  "revision": "manifest:...",
  "context": {
    "project_id": "HGC-MF-2026-001",
    "run_id": "RUN-MF-2026-0831",
    "mode": "live",
    "source_status": "local_event_store",
    "input_revision": "manifest:<64 hex>",
    "worktree_revision": "manifest:<64 hex>",
    "control_revision": "manifest:<64 hex>"
  },
  "prev_hash": "sha256:...",
  "event_hash": "sha256:..."
}
```

前端消费 `seq`，断线后用 `after_seq` 补发；不能按本地时间排序或重复应用副作用。事件应该先持久化，再广播。

## 2. 项目快照

`GET /api/projects/{id}/snapshot`

```json
{
  "project_id": "HGC-MF-2026-001",
  "run_id": "RUN-MF-2026-0831",
  "revision": "manifest:...",
  "tasks": [{"id":"G7","status":"BLOCKED","owner":"critic"}],
  "messages": [],
  "next_seq": 42,
  "approvals": [],
  "relays": [],
  "agent_sync": {"antigravity":"PENDING_RELAY"},
  "event_chain_valid": true
}
```

`context.input_revision`、`context.worktree_revision` 和
`context.control_revision` 必须在首屏、任务详情和证据详情保持一致；它们
分别表示输入快照、工作区结果和控制面事件投影。真实服务端运行必须使用
完整 `manifest:<64 hex>`；离线前端 fixture 可以使用带 `fixture:` 前缀的可读
ID，但必须保持 `SIMULATED · fixture`，不能以它冒充完整性证明。

## 3. 写入消息

`POST /api/projects/{id}/messages`

```json
{
  "text": "请给出最小反例并附运行命令",
  "sender_id": "owner",
  "channel": "validation",
  "mode": "full",
  "claim_class": "hypothesis",
  "task_id": "G7",
  "subproblem_id": "Q4",
  "evidence_refs": ["artifact:counterexample-v2"],
  "target_revision": "manifest:<64 hex>",
  "base_revision": "manifest:...",
  "idempotency_key": "ui-unique-key"
}
```

消息投影会保留上述建模 provenance，并返回 `status: RECEIVED`。缺少
`claim_class/task_id/subproblem_id/evidence_refs` 时，前端必须显示
`unknown/UNVERIFIED`，不能从颜色或自然语言猜测。

返回 `409 STALE_REVISION` 时，客户端必须重新读取 snapshot；不能自动覆盖。重复的 `idempotency_key` 返回第一次事件，不再次触发模型或外部副作用；如果同一个 key 对应不同请求指纹，返回 `409 IDEMPOTENCY_CONFLICT`。

## 4. 本地开发 API 的控制面动作

```text
POST /api/projects/{id}/dispatch       # 注册 task envelope，不代表完成
POST /api/tasks/{id}/claim             # 取得 lease + fencing_epoch
POST /api/tasks/{id}/result            # 持有者提交 READY_FOR_REVIEW/FAILED 回执
POST /api/tasks/{id}/heartbeat         # 续租，拒绝过期/旧 epoch
POST /api/tasks/{id}/handoff            # 在持有者之间显式交接
POST /api/tasks/{id}/review             # accept/revise/reject 状态门
GET  /api/tasks/{id}/findings           # 查看 P0/P1/P2 finding
POST /api/tasks/{id}/findings/{fid}/close # 用证据关闭 finding
POST /api/projects/{id}/approvals       # 仅 Owner 记录审批，不自动执行
POST /api/relays                        # 生成外部冻结包，默认 PENDING_RELAY
POST /api/relays/{relay_id}/ack         # 校验 nonce/input_hash 的 connectivity ACK
GET  /api/model-profiles                # 当前能力注册表（不含凭证）
POST /api/model-route                   # 只读 capability-first 路由预览，不调用模型
POST /api/runs/{run_id}/rerun           # 记录复跑请求
```

开发服务把 `revision` 写入事件响应，前端可用它维持 CAS 游标；事件断线后按 `after_seq` 回放，不能只依赖聊天时间排序。为方便离线 bootstrap，开发版 `dispatch/relay/message/approval` 的 `base_revision` 可以省略（此时只做串行追加，不提供并发冲突保护）；生产版应将其改为必填，或使用服务端明确的首个 revision。

## 5. 任务声明与回执

任务可以关联一个或多个 `subproblem_id`，也可以声明共享工件：

```yaml
subproblem_ids: [Q1, Q2]
shared_artifact_ids: [clean-data-v1]
```

共享节点只运行和计数一次；每个 Q 通过映射引用它。不能复制整条
G0—G16 轨迹来制造覆盖率。

任务 dispatch 必须声明：

```yaml
task_id: G11-Q2
owner_id: solver-q2/session-...
reviewer_id: validator/session-...
depends_on: [G10]
input_revision: manifest:...
write_set: [artifacts/solver/Q2/**]
capabilities: {read: [data/clean/**], code_exec: true, network: false, secrets: false}
acceptance:
  - python scripts/run_q2.py --seed 20260831 exits 0
  - result.json includes units and claim_ids
lease: {ttl_seconds: 1800, fencing_epoch: 7}
```

回执必须同时提供：`status`、`target_worktree_revision`、changed paths、artifact hash、claim/evidence、命令/退出码、环境、假设、未完成项、风险和下一动作。开发 API 的 `result` 至少要求 `artifact_refs`、`evidence_refs`、`commands`、`result_hash`、`fencing_epoch` 和当前控制 `target_revision`；显式建模回执还要提供 `problem_type`、至少两个不同 `validation_checks`（每项含 `scope/threshold/exit_code=0/result_hash`）。`artifact_manifest`、`paper_claims` 和 `provenance_gate` 用于把文件与论文数字绑定；没有 `READY_FOR_REVIEW`、数值验证门或 manifest provenance 的回执不能 accept。

## 6. Review 与 Owner 审批

### 本地知识库引用

资料包由只读 KB adapter 提供，不给 Agent 任意路径读取权。检索使用：

```text
GET /api/projects/{project_id}/knowledge/search?q=...
GET /api/projects/{project_id}/knowledge/context?q=...
```

返回的 `kbdoc:kbdoc_<16位hex>` 是文档级来源指针；消息层允许挂载它，但它不等于 `artifact_manifest`，也不能单独推动 `READY_FOR_REVIEW`、`VERIFIED` 或 `RELEASED`。发布门会再次解析 KB 文档是否存在且仍处于 `LOCAL_INDEXED`；页级 `kbchunk` 在 OCR/chunk 切片完成前保持阻断。

Review 需要 `target_revision`、reviewer identity、非作者的 `independence_basis`、至少一条 `check_logs`、至少一条 `evidence_refs`、verdict 和 finding closure。服务端门禁：

```text
if open(P0 or P1) and not owner.accepted_risk:
    reject ACCEPTED / RELEASED
if artifact.provenance not in {verified, accepted}:
    reject paper_numeric_claim
if approval.scope does not cover action:
    reject external_send / publish / delete
```

Owner 审批记录 `approval_id、scope、snapshot、decision、created_at、expires_at、revoked_at`。外部 relay 必须引用一条未过期、scope 匹配、target revision 匹配的 `approve` 记录；`accept_risk` 只用于显式风险豁免。Agent 评分仅作为 decision support。

## 7. ModelGateway

```python
result = gateway.run(
    capability={"long_context_reasoning", "local_files"},
    role="model_strategist",
    context_packet=packet,
    budget=budget,
    isolation="blind",
)
```

Gateway 根据 capability、风险、数据驻留、预算和 calibration 分数选择实际 provider/model，并记录：

```yaml
provider: openai
model: gpt-5.6-terra
version: resolved
reasoning_effort: high
tool_permissions: [read_local, python_sandbox]
input_manifest: manifest:...
output_hash: sha256:...
token_in: 0
token_out: 0
latency_ms: 0
cost_snapshot: null
fallback_used: false
```

## 8. 外部 relay

跨平台只传冻结快照、任务边界和验收，不复制整段聊天。Relay 至少包括：

```yaml
relay_id: RELAY-001
from_id: codex/root/session-abc
to_id: antigravity/reviewer/workspace-1
nonce: ...
issued_at: ...
expires_at: ...
input_revision: manifest:...
approval_ref: owner-approval-...
signature_or_mac: ...
```

未完成身份验证、输入哈希确认和 ACK 时，前端显示 `PENDING_RELAY`。一次 ACK 只证明 connectivity smoke test 通过，不代表持续在线同步。事件序号接口支持 `limit`（1–500）并返回 `has_more/next_after_seq`；客户端必须按 `seq` 连续回放。

## 9. 能力目录与工作流装配契约

能力层把资料库中的可迁移结构投影为方法卡、工作流块、题型 archetype 和内容包。它只产生候选能力，不执行模型、代码或原始文件读取；每个返回对象都应能回到 `source.index_revision` 和 `source_refs`。能力目录变化时，旧 `capability_revision` 只能用于只读比较，不能写入当前装配。

### 9.1 读取目录与题型建议

```http
GET /api/projects/{project_id}/capabilities/catalog
GET /api/projects/{project_id}/capabilities/suggest?q=约束优化&limit=8
```

目录响应的关键字段如下：

```json
{
  "schema_version": "capability-catalog/v1",
  "capability_revision": "cap:<64 hex>",
  "source": {"index_revision": "kb:<64 hex>", "source_status": "LOCAL_PENDING"},
  "workflow_blocks": [{
    "id": "validation", "kind": "validation",
    "input_ports": {"model": "model", "result": "result", "baseline": "result"},
    "output_ports": {"validation_report": "validation_report"},
    "required_inputs": ["model", "result"], "required": true,
    "agent_roles": ["validation_auditor"],
    "validation_kinds": ["error", "sensitivity", "robustness"]
  }],
  "methods": [{
    "id": "ridge-regression", "family": "prediction",
    "applicability": ["连续响应", "样本量有限"],
    "prohibitions": ["时间泄漏未处理"],
    "validation_checks": ["独立留出", "残差检查"],
    "claim_class": "inferred", "source_refs": ["kbdoc:kbdoc_<16位hex>"]
  }],
  "content_packs": [{
    "id": "counterexample", "title": "反例与边界",
    "description": "敏感性、失败模式、禁用条件",
    "query": "敏感性分析 误差 适用条件 反例",
    "archetype_ids": ["all"],
    "required_outputs": ["prohibitions", "independent_review"],
    "claim_class": "inferred", "source_refs": []
  }],
  "workflow_presets": [], "problem_archetypes": []
}
```

`suggest` 是透明 cue-based 建议：命中的关键词、分数和推荐都属于 `hypothesis`，不能被当作题型判定。正式建模仍要以题面契约、数据审计和领域约束为准。

当前 MVP 没有独立的 `content_packs` CRUD 资源端点；内容包作为能力目录的一等对象返回，并通过只读 resolve 接口绑定当前检索候选，再在装配请求中用 `content_pack_ids` 挂载。它们仍是检索与审查清单，不是论文事实。持久化或由资料片段生成新包时，必须复用同一 `capability_revision`、来源引用和 claim 分层，不能把“内容包已挂载”当作已验证结论。

只读解析接口：

```http
GET /api/projects/{project_id}/capabilities/content-packs/{pack_id}/resolve?top_k=6
```

服务器只允许目录中已注册的 `pack_id`，用该包的固定 query 在当前知识库快照上做有界检索，不打开目录外文件、不执行代码。响应至少包含：

```json
{
  "pack_id": "counterexample",
  "index_revision": "kb:<64 hex>",
  "source_status": "LOCAL_PENDING",
  "coverage": {"metadata_candidates": 123, "returned": 6, "body_examined": 6},
  "evidence_refs": ["kbdoc:kbdoc_<16位hex>"],
  "results": [{
    "citation_ref": "kbdoc:kbdoc_<16位hex>",
    "path_rel": "…",
    "extract_status": "TEXT_EXTRACTED",
    "usage": "反例与边界",
    "claim_class": "observed"
  }],
  "warnings": ["页级定位尚未完成"]
}
```

`evidence_refs` 只证明候选来源已被当前快照返回；它不能单独关闭反例、敏感性或论文发布门。装配提交可以把解析后的 refs 作为审查上下文，但仍需独立复现。

### 9.2 动态题面契约

```http
POST /api/projects/{project_id}/capabilities/problem-contract
Content-Type: application/json
```

```json
{"text":"问题一：建立预测模型……\n问题二：在约束下求最优方案……", "source_refs":["artifact:problem-statement"]}
```

响应固定为 `status=DRAFT_UNVERIFIED`，并返回确定性 `revision=sha256:<64 hex>`：

```json
{
  "contract_version": "problem-contract/v1",
  "status": "DRAFT_UNVERIFIED",
  "revision": "sha256:<64 hex>",
  "subproblems": [{
    "id": "问题一", "prompt_excerpt": {"value":"…", "claim_class":"observed", "evidence_refs":["artifact:problem-statement"]},
    "variables": {"value":["unknown"], "claim_class":"observed"},
    "constraints": {"value":["…"], "claim_class":"observed"},
    "validation_prompts": {"value":["unknown"], "claim_class":"observed"}
  }],
  "archetype_cue_suggestions": [{"id":"optimization", "score":1, "claim_class":"hypothesis"}],
  "uncertainties": ["语义、单位、题目范围和事实真值均未独立核验"]
}
```

抽取器是保守的词法/分段工具；它不确认隐含变量、单位、因果机制、附件含义或正确答案。无编号题面会得到 `Q1` 草稿。Scope-Lock 必须把该草稿修订为人工确认的题面覆盖表后，才能用于路线审批。

### 9.3 干运行组合校验

```http
POST /api/projects/{project_id}/capabilities/compose
Content-Type: application/json
```

```json
{
  "nodes": [
    {"node_id":"decomp","block_id":"problem-decomposition","config":{}},
    {"node_id":"audit","block_id":"data-audit","config":{}},
    {"node_id":"base","block_id":"baseline-model","method_id":"linear-regression","config":{}},
    {"node_id":"check","block_id":"validation","config":{}},
    {"node_id":"write","block_id":"writing","config":{}}
  ],
  "edges": [
    {"source":"decomp","source_port":"subproblems","target":"base","target_port":"subproblem"},
    {"source":"audit","source_port":"data_contract","target":"base","target_port":"data_contract"},
    {"source":"base","source_port":"model","target":"check","target_port":"model"},
    {"source":"base","source_port":"result","target":"check","target_port":"result"},
    {"source":"base","source_port":"result","target":"check","target_port":"baseline"},
    {"source":"decomp","source_port":"subproblems","target":"write","target_port":"subproblems"},
    {"source":"base","source_port":"result","target":"write","target_port":"result"},
    {"source":"check","source_port":"validation_report","target":"write","target_port":"validation_report"}
  ],
  "scope":["Q1"], "idempotency_key":"ui-compose-001",
  "content_pack_ids":["problem-evidence","counterexample"],
  "innovation_card":{"baseline":"透明线性基线","difference":"加入滚动回测","necessity":"处理时间漂移","boundary":"超出样本域退回基线","validation":"固定种子 clean-run","subproblem_id":"Q1"},
  "previous_nodes":[], "previous_edges":[]
}
```

服务器重新检查 block/method 引用、端口类型、必需输入、DAG 无环、模型→验证链和四个产品硬门：
`problem-decomposition`、`baseline-model`、`validation`、`writing`。响应返回 `status`、`assembly_revision=assembly:<64 hex>`、`validation`、`diff=assembly-diff/v1`、`required_block_ids`、`custom_block_count`、`method_block_warnings`、`innovation_card/innovation_gate` 和 `content_pack_ids/content_packs`。`compose` 是 dry-run，不追加事件。创新卡始终被服务端降级为 `claim_class=hypothesis`。

节点可以带 `parameter-contract`、`scenario-contract`、`critic-challenger` 等扩展；自由装配允许增加节点和替换方法，但不能移除硬门或把类型不匹配的输出强接到输入。结构校验通过不代表模型数学正确、参数可识别、数据无泄漏或结果稳定。

### 9.4 提交装配、CAS 与事件同步

```http
POST /api/projects/{project_id}/capabilities/commit
Content-Type: application/json
```

```json
{
  "actor_id":"owner", "nodes":[], "edges":[],
  "assembly_revision":"assembly:<64 hex>",
  "capability_revision":"cap:<64 hex>",
  "source_revision":"kb:<64 hex>",
  "base_revision":"manifest:<64 hex>",
  "previous_assembly_revision":"assembly:<64 hex>",
  "content_pack_ids":["problem-evidence","counterexample"],
  "innovation_card":{"baseline":"透明线性基线","difference":"加入滚动回测","necessity":"处理时间漂移","boundary":"超出样本域退回基线","validation":"固定种子 clean-run","subproblem_id":"Q1"},
  "action":"SUBMIT_REVIEW",
  "idempotency_key":"ui-commit-001"
}
```

`action=SAVE_DRAFT` 可保存结构不完整的草稿；`action=SUBMIT_REVIEW` 要求 `validation.valid=true`，即硬门、端口、依赖和证据链全部通过。服务端会以同一目录快照重建装配并重新计算 revision：客户端传来的 `assembly_revision`、`capability_revision` 或 `source_revision` 过期时返回 `409`，不得覆盖或自动合并。

成功提交追加一个 `type=ASSEMBLY_UPDATED`、`channel=assembly` 的 append-only 事件，payload 至少包括 `assembly_revision`、`capability_revision`、`action`、`status` 和 `diff`。snapshot 的 `assembly` 是该事件的最新投影；群聊只是它的通知视图。客户端应按事件 `seq` 回放，重复 `idempotency_key` 返回首次结果，不重复追加副作用。

`previous_assembly_revision` 是装配投影级 CAS：它防止两个浏览器同时修改同一画布。`base_revision` 是整个控制面事件链的 CAS：它防止旧任务/旧聊天覆盖新控制面。两者都不是数学正确性证明；后者冲突时应重新读取 snapshot、人工确认差异后再提交。

### 9.5 差异审计与创新声明

`assembly-diff/v1` 的 `added_nodes`、`removed_nodes`、`changed_nodes`、`added_edges`、`removed_edges` 和 `impacted_nodes` 描述可复现的结构变化，`missing_required_blocks` 与 `status` 描述硬门状态。它适合做群聊同步、Owner 审批和回滚依据。

差异本身不自动生成 `originality` 或“创新点”。若要声称创新，必须创建独立差异卡，说明相对 baseline 的假设/机制/算法/数据或验证变化，并提供消融、敏感性、反例或 clean-run 证据；否则 claim class 只能保持 `hypothesis`。

### 9.6 当前边界

能力目录目前是从 metadata/受限短片段和内置能力卡投影出的离线开发版；它不等于 18,986 份资料已完成全文理解、页级 OCR、向量检索或人工审核。系统可以对未知题型保留通用接口并允许人工装配，但不能保证“所有赛题自动正确建模”。正式论文数字、规则结论和获奖判断仍需当届官方来源、独立数学审查、数据验证和清洁环境复现。

## 10. Workspace / repo catalog（T07）

仓库协作资料与外部数学建模资料盘属于不同来源域。workspace catalog 只读挂载
已经进入版本控制的 `README.md`、`TASKS.md`、`AGENTS.md`、`app.js`、
`index.html`、`styles.css`、`docker-compose.yml` 以及 `backend/`、`assets/`、
`docs/`、`skills/`、`notes/`、`workflows/`、`models/`、`paper/`、`viz/`、
`scripts/`、`experiments/`，不扫描用户资料根、不读取 secrets、不执行仓库文件。

```http
GET /api/projects/{project_id}/workspace/catalog
GET /api/projects/{project_id}/workspace/search?q=&top_k=20&path=docs
```

两接口均返回 `manifest_sha`（兼容别名 `manifest_sha256`）、`items`、`counts` 和
`repo:<relative-path>` `source_refs`；search 还返回有界 `snippet`、
`match_source` 与 `retrieval_boundary`。文本正文检索上限 1 MiB，hash 上限和
`top_k` 也有限制。绝对路径、盘符路径、`..` 穿越、隐藏项和符号链接被排除或
返回 `400`；未知 project 返回 `404`。

### 10.1 source_integrity 与 repo 引用

`source_integrity=observed` 只表示路径在允许仓库根内、读取未执行文件、内容 hash/
大小状态与 manifest 可对照；它不表示文档观点正确、授权完备、题面适配或论文结论
成立。`repo:` 引用是可写入 `evidence_refs` 的候选上下文句柄，但不能单独当作足够的
证据、`VERIFIED` 或论文 claim。Agent 必须读取 manifest、检索候选、绑定当前题面/数据 revision，回到
文件核对后，再经过独立验证、artifact provenance 和 Owner 审批；manifest 变化时旧
context 标为 `STALE` 并重新检索。

该接口当前是离线开发版的 bounded lexical search，不承诺全文语义理解、向量召回、
页级 OCR、持久化 FTS 或生产级 RBAC/签名 relay。
