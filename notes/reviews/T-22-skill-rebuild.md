# T-22 Skill v2 重建复核记录

日期：2026-09-03
协调方式：SOLO（Owner 先前明确要求本次暂不调用其他 Agent）
基线：`77eb59c`（T-21 校赛 B 题求解完成）
工作分支：`task/T-22-rebuild-skills`
最终 Skill Registry revision：`skill:a3eea83d483593dc8bee551a142d38560f5363fa1c82efbb80b06d8d4d512372`

## 范围与来源

- 删除仓库 `skills/` 下旧扁平入口和两个旧技能目录；没有删除系统级
  `C:\Users\zyy20\.codex\skills`。
- 以 Owner 资料盘快照 `materials-inventory:2026-08-31` 为来源，清单摘要
  `a3eb5ea717a45dee3b280afc506b37df3026e7142a9f3411e5bdafe3bc4306a`。
- 来源哈希、证据类别、支持范围和版权边界集中登记在
  `skills/source-provenance.json`；原始资料、完整论文、模板和未知代码未复制。
- 校赛一等奖论文哈希登记为
  `6e330b3520ce57b4fa9de3674e3dead4eef7bcf0fcc20ad08af1264f3ba48eae`，仅用于数学
  推导与排版结构观察，不被当作高教社杯规则。

## 交付物

- 13 个核心技能 + 3 条工作流，每项有 `SKILL.md`、`agents/openai.yaml`、
  `skill-manifest.json`；
- 共享证据、产物、路由、评审、排版和拼图契约；
- 86 张候选方法卡，均有适用/禁用/假设/输入/输出/验证/fallback/skill_refs；
- `backend/skill_registry.py` 只读注册表 API，能力目录带
  `skill_registry_revision` 和方法绑定状态；前端显示绑定与 revision；
- registry、数据、运行、重建、拼图和论文正反例校验器，以及一键回归脚本。

## 已执行验收

| 检查 | 结果 |
|---|---|
| registry v2 strict（含来源 ID、依赖 DAG、引用和旧入口扫描） | PASS；16 entries，12 sources |
| skill-creator quick_validate | PASS；16/16 |
| workflow/data/run/reconstruction 正例 | PASS |
| workflow 负例 | PASS；按预期 exit 1 |
| 论文正反向夹具 | PASS |
| `node --check app.js workflow-puzzle.js` | PASS |
| backend pytest | PASS；158 passed |
| `git diff --check` | PASS |

统一复现命令：

```powershell
python -X utf8 skills/tests/run_regression.py
```

## 独立性与限制

这次是单 Agent 串行执行，按 charter 模拟 Scope/Producer/Critic/Challenger/Auditor
并留下结构化校验记录；它不是供应商之间的独立数学复算。回归只证明技能结构、契约和
边界有效，不证明任何新赛题的模型正确或论文能获奖。外部 Agent 适配器仍未连接，
生产部署仍需 OIDC/RBAC、持久化事件库、低权限求解沙箱、签名 relay 和 Owner 发布审批。

## 当前判定

`READY_FOR_REVIEW`：代码和契约可进入 Owner 审查；合并到 `main`、向外部 Agent
发送资料或发布具体论文仍需 Owner 明确批准。
