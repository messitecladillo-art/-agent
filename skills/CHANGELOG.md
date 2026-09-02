# Skill Registry 变更记录

## v2.0.0 · 2026-09-03 · T-22

### 删除

- 删除旧的扁平入口：`01–08` 阶段 Markdown 和两条旧 workflow Markdown；
- 删除旧的 `math-modeling-mathematical-writing`、`mhagent-evidence-reconstruction`
  技能入口。

删除范围仅限本仓库 `skills/`；系统级 `C:\Users\zyy20\.codex\skills` 不在范围内。
旧目录中曾有的可复用脚本、评测夹具、数学推导指南、范文模式卡和 MHAgent 契约已迁移到
新的分层目录，并更新所有当前调用方。迁移不会把原始论文或资料包复制进仓库。

### 新增

- 13 个核心技能：章程、安全、范围、拆题、数据、路由、推导、求解、验证、排版、范文、
  发布、美赛增量；
- 3 条工作流：高教社杯固定主流程、备赛训练、DIY 拼图；
- `registry.json`、`source-provenance.json`、16 个 manifest 和共享契约；
- 86 张候选方法卡，均含适用域、禁用条件、假设、输入输出、验证、fallback 和 skill refs；
- registry/API/契约/拼图/论文正反例校验器与一键回归脚本。

### 兼容与状态

- 所有路径改为仓库相对、可审计、拒绝 `..`/绝对路径/符号链接；
- registry 和来源台账内容参与 `skill_registry_revision`；
- 方法卡与技能绑定失败显示 `STALE`/`UNAVAILABLE`，不会静默回退旧入口；
- `SAVE_DRAFT`、`SUBMIT_REVIEW`、`RELEASE` 的状态门保持分离；
- 外部 Agent 未连接时仍只生成 `PENDING_RELAY`，不声称实时同步。

### 回归命令

```powershell
python -X utf8 skills/tests/run_regression.py
```

负例以“按预期被拒绝”计为通过；回归通过不等于任何具体赛题的数学结论已经被证明。
