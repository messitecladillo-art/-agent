# Skill 库与 Workflow 索引

> 本目录是团队的"方法论层"：把官方评阅标准、近十年模范论文规律蒸馏成可执行的技能与流程。
> 事实基础（部分为 Owner 本地资料盘/历史输入，非运行时硬依赖）：`资料包/01/官方评阅标准/`（2004–2024，含 2005–2018 逐年要点与 2010B 评分细则）+ `资料包/06` 写作指南 43 件 + `资料包/09` 美赛方法论 + `notes/exemplary-paper-breakdown.md`；当前 checkout 可直接读取的规则与模式以 `docs/`、`notes/` 和各 Skill 文件为准。
> 维护：Qoder 主责；skill 更新走正常任务流程（TASKS.md 登记、提交说明来源）。

## 阶段 × Skill × 主责 速查表

| 阶段 | Skill | 主责 | 产出落点 |
|---|---|---|---|
| 0 审题破题 | `01-审题破题.md` | Qoder | `notes/problem-analysis.md` |
| 1 建模 | `02-模型选型与建模.md` | Qoder | `models/README.md` |
| 2 求解 | `03-求解与实现.md` | Codex | `models/` + `experiments/` |
| 3 验证 | `04-验证与灵敏度分析.md` | Codex（Qoder 审） | `experiments/log.md` |
| 4 写作 | `05-论文写作.md` | Qoder（Antigravity 图） | `paper/` |
| 横切写作门 | `math-modeling-mathematical-writing/SKILL.md` | Qoder/Codex + 独立 Critic | `paper/` + equation/claim/crossref/render manifest |
| 5 终检 | `06-论文评审与终检.md` | review.py + Qoder | `notes/reviews/` |
| 辅助 | `07-范文精析.md` | Qoder / Claude API 批量 | `notes/paper-notes/` |
| 专项 | `08-美赛专项.md` | Qoder | 打美赛时叠加在 01–06 之上 |
| 证据迁移 | `mhagent-evidence-reconstruction/SKILL.md` | Codex + 独立 Critic/Auditor | `docs/mhagent-reconstructed-workflow.md` |

配套清单：`notes/算法模板盘点.md`（T-07 施工蓝图，七类模板候选 + 移植要点 + 缺口）。

## 两条 Workflow

| Workflow | 场景 | 文件 |
|---|---|---|
| 比赛主流程 | 比赛日 72 小时作战：阶段×角色×评审门×时间盒 | `workflow-比赛主流程.md` |
| 赛前冲刺流程 | 备赛期 4–8 周：评审校准→精析→模板库→演练→装箱 | `workflow-赛前冲刺流程.md` |

## 使用规则

1. **派发任务时指定 skill**：如"按 `skills/02` 完成子问题 2 的模型决策记录"
2. **评审门不可省**：每个阶段产出必须过对应评审门才进入下一阶段
3. **skill 是活的**：演练与实战中发现的规律回写对应 skill（来源注明年份与出处）
4. **与守则的关系**：AGENTS.md 管"谁、在哪、怎么协作"，本目录管"每个阶段怎么做才对"

## 数学表达与排版 Skill（新增）

`math-modeling-mathematical-writing/` 是跨阶段的写作与证据门：把题面小问、变量/假设、
公式推导、离散算法、验证结果、图表和附录代码连成一条可回放链。它从用户提供的一篇
高分论文中只提炼结构模式（例如符号—单位登记、公式/图表交叉引用、情景与验证的组织），
不复制论文文字、图、代码、参数或结论，也不把单篇论文的字号、页数、字体、章节名当成
官方规则。

入口文件之外，按需读取：

- `references/reference-paper-pattern-card.md`：观察事实、可泛化规则与不适用边界；
- `references/derivation-and-layout-guide.md`：推导卡、LaTeX/Word 片段、图表与渲染门；
- `references/registries-and-evidence.md`：`equation_registry`、`crossref_manifest`、
  `claim_matrix`、验证和发布状态 schema；
- `scripts/audit_latex_math.py`、`scripts/audit_paper_contract.py`：无依赖/低依赖的结构检查；
- `evals/`：可重复的正反例前向夹具。

使用时必须先锁定当前竞赛版本与官方格式；结构检查通过不等于数学正确，仍需独立推导、
数据审计、干净编译、视觉 QA 和 Owner 审批。

## 运行证据反推 Skill（新增）

`mhagent-evidence-reconstruction/` 只负责把外部 Agent 的导出结果包映射为七步能力契约：
输入、产物、方法链、验证门、交接和未决项。它是现有 01–08 Skills 与拼图工作台的
迁移/审计层，不会覆盖或替换原有方法卡；契约默认 `READY_FOR_REVIEW`，只有独立复核
关闭证据冲突后才可升级。入口脚本为 `scripts/validate_step_contract.py`，详细证据边界见
`docs/mhagent-reconstructed-workflow.md`。

## 内嵌的五条官方金律（所有 skill 的共同底座）

1. 结果可对表　2. 定义即得分点　3. 模型 > 算法 > 数值　4. 约束逐条验证　5. 拒绝模板腔
