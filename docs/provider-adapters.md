# Provider Adapter 接入手册

## 1. 总原则

不要让每个产品各自维护一套“聊天上下文”。所有供应商都只接收一个受限的 `task_packet`，返回 `result/handoff`，由 Coordinator 写入统一事件源。跨产品协作传的是冻结快照、任务边界和证据引用，不是整段群聊。

统一接口：

```text
submit(task_packet) -> run_id
poll(run_id) -> status
fetch_output(run_id) -> result_envelope
send_followup(run_id, prompt) -> run_id
cancel(run_id) -> status
```

每个 adapter 必须实现：固定参数/JSON 输入、超时、输出上限、重试与幂等、取消、run 所属关系校验、日志脱敏和 `provider/model/version` 记录。不可执行的能力必须返回 `MODEL_UNAVAILABLE`，不能伪造成功。

## 2. Codex

### 最适合

- 根 Coordinator、长上下文规划、主路线 A、代码/工具执行、集成与冲突仲裁。
- 当前桌面会话可以使用原生多 Agent 协作能力；根任务负责 spawn、follow-up、wait、interrupt 和最终汇总。

### 约束

- 子 Agent 默认 `max_depth=1`，不得自行再派 Coordinator。
- 子 Agent 的提示词只包含 task packet/context packet，不复制整个群聊。
- 关键数学结论仍需要独立模型/独立会话和运行证据，不能因为是同一平台就算独立验证。

## 3. Claude

### 最适合

- Independent Solver B、长文档批评、论文二审、反例与假设审查。

### 接入

可通过官方 API、CLI 或人工 relay 实现 `submit/poll/fetch`。建议每次新建独立上下文，并只读冻结的题面契约和数据摘要。若没有可调用 connector，使用 `.collab/relay/`，状态保持 `PENDING_RELAY`。

## 4. Qoder

### 最适合

- Data Auditor、Python/SQL 清洗、算法实现、测试、结果表自动生成。

### 权限

- 可读题目数据和批准的代码目录，可写自己的 solver/data 分支。
- 默认无外网、无 secrets、无发布/删除权限。
- 所有运行必须记录命令、退出码、环境、随机种子和输入 manifest。

## 5. Antigravity

### 最适合

- Vision/OCR、图表/公式抽取、第二家独立 Challenger、外部审查团队。

Antigravity 的 Teamwork/MCP/Headless 能力可作为 adapter 目标，但必须先通过 connectivity smoke test：

```text
发送 read 请求 → 收到 authenticated ACK → 核验 input hash
→ 返回 bounded result → Coordinator 写入 review 工件
```

ACK 只说明一次连接测试通过，不等于持续实时同步。当前本机 Codex 环境没有已验证的 Antigravity connector，因此前端默认显示 `PENDING_RELAY`；建立 adapter 后再改为 `CONNECTED/VERIFIED`。

## 6. 其他模型

### OpenAI-compatible API

统一用 `base_url + model + capability profile` 注册，不把供应商名写进业务逻辑。生产环境记录数据驻留和条款，测试环境用 fake adapter 验证状态机。

### MCP server

只暴露窄操作：`claim_task`、`read_context`、`append_event`、`put_artifact`、`request_review`、`heartbeat`。MCP 是传输层，不能代替 durable event store。

### 人工 relay

当模型无法自动连接时，群主或队员可以把固定 YAML relay 包交给外部产品，再把返回文件放入指定 review 目录。人工 relay 也必须带 input hash、ACK、过期时间和回执；不能把手工复制称为自动同步。

## 7. 连接状态

```text
DISCOVERED      已登记能力，但未运行
SUBMITTED       已发送 task packet
ACKED           收到回执，等待结果
CONNECTIVITY_VERIFIED  输入 hash 与身份核验通过
RUNNING         有有效 lease/heartbeat
PENDING_RELAY   connector 不可用，等待人工或后续 adapter
MODEL_UNAVAILABLE  没有满足能力/数据策略的模型
FAILED / TIMEOUT / CANCELLED
```

前端状态必须来自事件源，不能由“模型说自己完成”直接变绿。

