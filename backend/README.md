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
- `GET /api/projects/{project_id}/latex/toolchain`
- `POST /api/projects/{project_id}/latex/compile`（显式入队；固定参数、超时、日志上限）
- `GET /api/projects/{project_id}/latex/jobs/{job_id}`
- `GET /api/projects/{project_id}/latex/jobs/{job_id}/pdf`（仅 `SUCCEEDED` 且路径通过白名单时开放）
- `WS /ws/projects/{project_id}`
- `GET /api/projects/{project_id}/knowledge/summary`（只读资料盘点）
- `GET /api/projects/{project_id}/knowledge/search` / `retrieve`（限量检索与短片段）
- `GET /api/projects/{project_id}/knowledge/context`（给模型适配器的 prompt-sized 资料包）
- `GET /api/projects/{project_id}/knowledge/documents/{doc_id}`（来源预览）
- `GET /api/projects/{project_id}/knowledge/documents/{doc_id}/file`（Owner 明确点击后打开白名单文件）
- `GET /api/projects/{project_id}/skills/catalog`（Skill Registry v2，只读）
- `GET /api/projects/{project_id}/skills/search?q=&limit=`（有界检索技能/工作流）
- `GET /api/projects/{project_id}/skills/{skill_id}`（manifest + 有界入口预览）

知识库默认读取 `C:\Users\zyy20\Desktop\数学建模资料全套包`，也可用环境变量
`GAOJIAO_MATERIALS_ROOT` 指定根目录。原始资料不复制到仓库、不执行其中代码；索引只保留
相对路径、文件元数据和按需抽取的短片段。`.qkdownloading` 等同步临时文件会被排除，目录
仍在同步时状态显示为 `LOCAL_PENDING`。摘要接口默认不返回完整文件清单，避免把数 GB 资料一次
传到浏览器；检索结果使用严格格式的 `kbdoc:kbdoc_<16位hex>` 文档级引用，不能绕过现有 validation/artifact/release 门禁；当前切片尚未承诺 PDF 页码级 `kbchunk` 定位。

本地服务提供原子 revision/CAS、完整 SHA-256 revision、请求指纹幂等、事件序号/分页、`prev_hash → event_hash` 日志链、断线补发、任务 lease/fencing/reclaim、结果回执、Owner 审批门和 `PENDING_RELAY` 外部边界。revision 输入必须是 `manifest:<64 hex>` 或 `source:<64 hex>`；显式建模结果还会经过题型、双检查族、scope/threshold、exit code 和结果 hash 的 `validation_gate`，并在 accept/release 前检查 `artifact_manifest` 与 `paper_claims` 的 provenance。旧适配器结果保留为 `UNVERIFIED` 迁移状态，不能直接验收。默认状态在内存中；设置 `COLLAB_STATE_FILE=runtime/collab-state.json` 可启用单进程的原子 JSON journal，进程重启后可恢复。它不等同于多进程数据库；生产版必须替换成 SQLite WAL/Postgres、OIDC/RBAC、真正的签名 relay、文件沙箱和审计存储。`COLLAB_RELAY_SECRET` 仅用于本地 HMAC 演示，不能当生产身份系统。

LaTeX/PDF 编译器是任务抽屉里的显式实时 job：工具链探测、`QUEUED → RUNNING → SUCCEEDED/FAILED/TIMED_OUT` 状态和 `LATEX_COMPILE_*` 事件沿用同一 revision/CAS/幂等/WebSocket 边界。入口仅允许仓库相对 `.tex` 文件，输出隔离在 `runtime/latex/<job_id>/`，不会通过静态 catch-all 暴露。详见 [`docs/latex-pdf-live-compiler.md`](../docs/latex-pdf-live-compiler.md)。当前实现为单进程、本地受信源 MVP，不能直接当公网沙箱；目标服务器必须重新探测 XeLaTeX/Poppler，并在生产部署前补上持久化队列、低权限沙箱、网络禁用、OIDC/RBAC 与下载鉴权。

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

## Workspace / repo catalog（T07）

Agent 可通过以下只读接口挂载仓库协作上下文：

```text
GET /api/projects/{project_id}/workspace/catalog
GET /api/projects/{project_id}/workspace/search?q=&top_k=&path=
```

catalog 仅扫描仓库白名单：`README.md`、`TASKS.md`、`AGENTS.md`、`app.js`、
`index.html`、`styles.css`、`docker-compose.yml` 以及 `backend/`、`assets/`、
`docs/`、`skills/`、`notes/`、`workflows/`、`models/`、`paper/`、`viz/`、
`scripts/`、`experiments/`。`.git`、`.collab`、`runtime`、`.env`、隐藏项和
符号链接永不进入索引。响应包含 `manifest_sha`（兼容别名
`manifest_sha256`）、相对路径 `items`、按类型 `counts` 和
`repo:<relative-path>` `source_refs`；搜索片段限制为 1 MiB 文本文件，
`top_k`、查询长度和结果均有上限。

`source_integrity` 的最低解释是：路径在允许的仓库根内、内容 hash/大小状态
与返回的 manifest 一致、读取过程未执行文件。它不表示文档内容正确、题目适配
或授权状态已确认。`repo:` 引用只能作为候选上下文；写入论文或发送给外部 Agent
前，仍须绑定当前题面/数据 revision，完成独立验证、artifact provenance、Owner
审批和外发授权。manifest 变化时旧上下文必须标记 stale，不能静默复用。

当前实现是每次请求的进程内扫描，并非持久化 FTS/向量库；超大文件可能只返回
 metadata，语义检索、页级定位、OCR 和生产级 RBAC/签名 relay 尚未由该接口承诺。

### Skill Registry v2

`skills/registry.json` 是技能发现的唯一事实源。它登记 13 个核心技能和 3 条工作流，
每项都带 `skill-manifest.json`、输入/输出、依赖、写集、来源 ID 和硬门。能力目录中的
每张方法卡还返回 `skill_refs`、`skill_binding_status`，把“候选方法”绑定到负责路由、
推导、求解、验证或发布的技能；绑定只说明程序入口，不证明该方法适合当前题目。

注册表接口只读、只返回相对路径和不超过 500 字的入口预览，不执行 SKILL、脚本或资料盘
代码。每次注册表或引用资源变化都会生成新的 `skill_registry_revision`；已有装配若引用
旧 revision 必须标记 stale 并重新校验。仓库根目录的一键回归命令为：

```powershell
python -X utf8 skills/tests/run_regression.py
```
