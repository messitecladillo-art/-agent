# 产品化落地路线

## 1. 目标用户与核心场景

### 用户

你是参赛队的群主/项目 Owner；队员可以是人、Codex、Claude、Qoder、Antigravity 或临时领域专家。系统默认面向一支队伍，而不是开放式公共聊天室。

### 三个高频场景

1. **读题决策**：上传官方赛题与附件，Scope/Rule/Vision/Data/Domain 自动形成可审批的题面契约。
2. **路线争论**：Model-A/B 互盲出方案，Critic/Challenger 以证据和反例推动 rebuttal，Owner 选择主线与回退线。
3. **临近提交**：Solver/Validation/Paper/Release 围绕同一冻结 revision 工作，红灯门禁阻止未经验证的数字进入论文或提交包。

## 2. MVP 与生产版边界

### 当前 MVP

- 无依赖静态前端：可直接打开或用 `python -m http.server`。
- 三栏工作台、频道、群主审批、Agent 卡片、DAG、证据预览、事件流和模拟回执。
- FastAPI 本地 API：snapshot、events（带分页）、dispatch、messages、claim/result/heartbeat/handoff、review、finding、Owner approval、relay/ACK、model-profiles、只读 model-route 预览、rerun、WebSocket。
- 原子 revision/CAS、请求指纹幂等、租约 fencing 和断线按 seq 回放示范；`?live=1` 可连接本地 API。
- Mock 事件在界面显式标为 `SIMULATED`；Live 模式只同步本地事件源，写入失败显示 `LOCAL_PENDING`，不伪造 Agent 回执。

### 生产版必须补齐

- OIDC 登录、项目 RBAC、注册 actor/session/connector 身份。
- SQLite WAL（离线）或 Postgres（团队）+ append-only event repository。
- 真正的 lease/heartbeat/fencing/CAS 和跨进程锁；当前开发版已经在单进程内演示这些门禁，并明确标注其边界。
- Git worktree 或非 Git manifest/copy-on-write 工件存储。
- 模型网关：能力路由、版本锁定、成本/延迟记录、fallback、数据驻留策略。
- Python/LaTeX/优化器沙箱和资源限额。
- 签名/MAC relay、nonce/expiry/replay 防护、路径规范化、归档沙箱、秘密扫描。
- 审查门禁服务端化；前端不拥有“把红灯改绿”的权限。
- 外部 Agent adapter 的超时、重试、输出上限、URL allowlist、取消和审计。

## 3. 推荐仓库结构

```text
gaojiao-agent-collab/
  index.html / styles.css / app.js       # 当前可运行 UI MVP
  assets/                                # 低对比度品牌/背景资产
  backend/
    app.py                               # 本地 API
    model_gateway.py                     # capability-first 路由
    orchestrator.py                      # 状态机/写集/CAS 规则
    test_*.py                            # 协议单测
  docs/
    architecture.md
    agent-roster.md
    prompt-pack.md
    api-contract.md
    model-routing.yaml
    model-calibration.md
    ui-system.md
    productization.md
  .collab/                               # 每个比赛项目运行时生成，不进模板
```

## 4. 里程碑与验收

### M0：协议与状态机（1 天）

验收：必填字段、claim 分类、状态合法转换、幂等/重放、stale revision、写集冲突单测通过。

### M1：本地群聊（2–3 天）

验收：4 个逻辑 Agent（Coordinator/Scope/Model/Critic）可以从任务包到回执；前端按 event seq 渲染；断线后能补发。

### M2：数据与执行（3–5 天）

验收：Python/LaTeX/solver 在沙箱运行；结果由脚本生成；manifest、日志、随机种子和环境可复现。

### M3：多模型独立路线（3–5 天）

验收：A/B 互盲；实际 provider/model/version 被记录；Critic 不读作者解释；关键结论至少两条独立证据。

### M4：论文与发布（3–5 天）

验收：Paper 只消费 VERIFIED claim；Citation/Similarity/Release 审计可阻断 P0/P1、未验证数字和哈希漂移。

### M5：跨平台 relay（约 1 周）

验收：Antigravity/Claude/Qoder 适配器完成 connectivity smoke test、ACK、输入 hash、超时、重试、取消和 `PENDING_RELAY` 降级。

### M6：往届题回放（约 1 周）

验收：3–5 道往届题在隔离 gold 下完整回放；记录题面覆盖、数学正确、复现、Critic 命中、成本、延迟、返工和阻塞；未达阈值不得正式比赛启用 FULL。

## 5. 比赛运行手册

### 开赛前

- 锁定模型版本、提示版本、依赖、时区和离线备份。
- 用 smoke test 验证 PDF/OCR/Excel/Python/LaTeX/优化器。
- 预设预算比例：读题 10%、路线 25%、实现 35%、验证 20%、论文发布 10%；验证预算不可被摘要挤占。

### 进行中

- 每个关键阶段生成 checkpoint：scope、route、implementation、validation、release。
- 每 30–60 分钟由 Context Curator 压缩事实/推导/假设/未决，不把摘要当原件。
- Critic↔作者最多 2–3 轮；再争论就升级 Owner，避免无限循环。
- 任何模型切换、外部传输、范围变更、风险接受都记录 approval/event。

### 收尾

- 冻结结果 revision，停止非必要探索。
- 从干净环境重跑关键命令；重新生成所有图表和结果表。
- 做题面覆盖、引用/查重/匿名、文件命名、页数、依赖和压缩包检查。
- Owner 最终批准后才执行外部提交。

## 6. 产品指标

不要只看“消息数”或“用了多少模型”，而要看：

- 题面覆盖率、关键 claim 证据覆盖率。
- 数学/单位/性质测试通过率。
- 独立复现成功率、结果 hash 漂移率。
- Critic 发现率、P1 关闭时间、返工次数、冲突率、重复工作率。
- 单任务 token/费用/延迟、模型 fallback 次数、阻塞时间。
- 最终论文中未经验证数字的数量（目标为 0）。
