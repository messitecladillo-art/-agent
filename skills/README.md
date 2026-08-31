# Skill 库与 Workflow 索引

> 本目录是团队的"方法论层"：把官方评阅标准、近十年模范论文规律蒸馏成可执行的技能与流程。
> 事实基础：`资料包/01/官方评阅标准/`（2004–2024）+ `notes/exemplary-paper-breakdown.md`。
> 维护：Qoder 主责；skill 更新走正常任务流程（TASKS.md 登记、提交说明来源）。

## 阶段 × Skill × 主责 速查表

| 阶段 | Skill | 主责 | 产出落点 |
|---|---|---|---|
| 0 审题破题 | `01-审题破题.md` | Qoder | `notes/problem-analysis.md` |
| 1 建模 | `02-模型选型与建模.md` | Qoder | `models/README.md` |
| 2 求解 | `03-求解与实现.md` | Codex | `models/` + `experiments/` |
| 3 验证 | `04-验证与灵敏度分析.md` | Codex（Qoder 审） | `experiments/log.md` |
| 4 写作 | `05-论文写作.md` | Qoder（Antigravity 图） | `paper/` |
| 5 终检 | `06-论文评审与终检.md` | review.py + Qoder | `notes/reviews/` |
| 辅助 | `07-范文精析.md` | Qoder / Claude API 批量 | `notes/paper-notes/` |

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

## 内嵌的五条官方金律（所有 skill 的共同底座）

1. 结果可对表　2. 定义即得分点　3. 模型 > 算法 > 数值　4. 约束逐条验证　5. 拒绝模板腔
