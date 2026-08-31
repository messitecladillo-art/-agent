# Local API（MVP）

这是建模议事厅的离线开发 API，用于验证前端与事件源之间的边界。它不是生产安全配置，也不会自动调用 Codex、Claude、Qoder 或 Antigravity。

## 启动

在 `gaojiao-agent-collab` 目录运行：

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8787
```

打开 <http://127.0.0.1:8787/?live=1> 可让前端连接本地 snapshot/API/WebSocket。也可以继续用静态服务器查看纯演示模式。

## 已实现（离线开发版）

- `GET /health`
- `GET /api/projects/{project_id}/snapshot`
- `GET /api/projects/{project_id}/events?after_seq=...`
- `POST /api/projects/{project_id}/dispatch`
- `POST /api/projects/{project_id}/messages`
- `POST /api/tasks/{task_id}/claim`
- `POST /api/tasks/{task_id}/result`（持有 lease 的 worker 提交 READY_FOR_REVIEW/FAILED 回执）
- `POST /api/tasks/{task_id}/heartbeat`
- `POST /api/tasks/{task_id}/handoff`
- `POST /api/tasks/{task_id}/review`
- `GET /api/tasks/{task_id}/findings`
- `POST /api/tasks/{task_id}/findings/{finding_id}/close`
- `POST /api/projects/{project_id}/approvals`
- `POST /api/relays`（只生成受限 relay 包，不发送）
- `POST /api/relays/{relay_id}/ack`（校验 nonce/input hash 的 connectivity ACK）
- `GET /api/model-profiles`
- `POST /api/model-route`（只读能力路由预览，不会调用供应商）
- `POST /api/runs/{run_id}/rerun`
- `WS /ws/projects/{project_id}`
- `GET /api/projects/{project_id}/knowledge/summary`（只读资料盘点）
- `GET /api/projects/{project_id}/knowledge/search` / `retrieve`（限量检索与短片段）
- `GET /api/projects/{project_id}/knowledge/context`（给模型适配器的 prompt-sized 资料包）
- `GET /api/projects/{project_id}/knowledge/documents/{doc_id}`（来源预览）
- `GET /api/projects/{project_id}/knowledge/documents/{doc_id}/file`（Owner 明确点击后打开白名单文件）

知识库默认读取 `C:\Users\zyy20\Desktop\数学建模资料全套包`，也可用环境变量
`GAOJIAO_MATERIALS_ROOT` 指定根目录。原始资料不复制到仓库、不执行其中代码；索引只保留
相对路径、文件元数据和按需抽取的短片段。`.qkdownloading` 等同步临时文件会被排除，目录
仍在同步时状态显示为 `LOCAL_PENDING`。摘要接口默认不返回完整文件清单，避免把数 GB 资料一次
传到浏览器；检索结果使用严格格式的 `kbdoc:kbdoc_<16位hex>` 文档级引用，不能绕过现有 validation/artifact/release 门禁；当前切片尚未承诺 PDF 页码级 `kbchunk` 定位。

本地服务提供原子 revision/CAS、完整 SHA-256 revision、请求指纹幂等、事件序号/分页、`prev_hash → event_hash` 日志链、断线补发、任务 lease/fencing/reclaim、结果回执、Owner 审批门和 `PENDING_RELAY` 外部边界。revision 输入必须是 `manifest:<64 hex>` 或 `source:<64 hex>`；显式建模结果还会经过题型、双检查族、scope/threshold、exit code 和结果 hash 的 `validation_gate`，并在 accept/release 前检查 `artifact_manifest` 与 `paper_claims` 的 provenance。旧适配器结果保留为 `UNVERIFIED` 迁移状态，不能直接验收。默认状态在内存中；设置 `COLLAB_STATE_FILE=runtime/collab-state.json` 可启用单进程的原子 JSON journal，进程重启后可恢复。它不等同于多进程数据库；生产版必须替换成 SQLite WAL/Postgres、OIDC/RBAC、真正的签名 relay、文件沙箱和审计存储。`COLLAB_RELAY_SECRET` 仅用于本地 HMAC 演示，不能当生产身份系统。

### 一个最小 API 流程

```text
dispatch（Coordinator 创建 task envelope）
  → claim（Agent 取得 lease/fencing epoch）
  → heartbeat（续租）
  → result（artifact/evidence/command/hash 回执）
  → review（独立审查，不能跳过状态门）
  → approval（Owner 记录决定）
  → relay（外部 Agent 只收到冻结包，默认 PENDING_RELAY）
  → relay ACK（只证明 nonce/hash 对得上，不代表任务完成）
```

所有写请求都应保存响应中的 `revision`，下一次写入带上同一个 `base_revision`/`target_revision`；收到 `409 STALE_REVISION` 时先拉取 snapshot 并人工确认，不要静默覆盖。开发版要验证真实 provider 时，另行实现 `ModelAdapter`，不要把 API key 放进前端或事件 payload。
