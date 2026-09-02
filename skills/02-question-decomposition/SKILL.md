---
name: 02-question-decomposition
description: 将已锁定的赛题拆成逐小问、依赖 DAG、交付物和评审清单；适用于复杂、多目标或跨数据/机理/优化路线的题目，避免直接从模型名开始写。
---

# 小问拆解与交付物 DAG

本技能把题面映射成可并行又不丢依赖的工作包。它不决定最终算法，而是明确每个小问
要回答什么、需要哪些中间量、怎样证明“答到了”。

## 输入

- 已冻结 problem-contract；
- 题面和附件引用；
- 时间、人员/Agent 数量和允许的并行度；
- 可用模型/数据/工具能力目录。

## 输出

每个小问生成：

- question_id、prompt_ref、objective_kind；
- inputs、states、decisions、outputs、units；
- hard_constraints、soft_objectives、information_set；
- dependencies 和 downstream consumers；
- candidate evidence 和 validation expectations；
- owner、write boundary、时间盒、fallback；
- coverage_matrix（题面句 → 产物 → 论文位置）。

## 拆解流程

### A. 逐句转化

把题面每个问句改写成可检验句式：

目标对象 + 动作 + 条件 + 输出格式 + 可接受误差/范围。

“分析影响”至少拆成影响量定义、方向/效应量、识别或关联方法和边界；“给出方案”
至少拆成决策变量、可行性、成本/收益和执行表。

### B. 建立依赖

画有向无环图，区分：

- 数据依赖：字段、清洗、切分；
- 数学依赖：定义、参数、方程、初值/边界；
- 计算依赖：模型输出喂给优化/仿真；
- 证据依赖：验证、敏感性、claim；
- 写作依赖：公式/图表/结果进入章节。

共享变量只产生一个 canonical ID；若多个小问需要不同粒度，显式写转换。

### C. 设计“基本分”与“增量”

每个小问先写最小可交付 baseline，再写主路线增量、创新假设和验证。增量必须回答：
增加的机制/数据/算法改变了哪个结论？没有消融或对照就不得称创新。

### D. 生成评审对表

把当届官方评阅要点中与该小问相关的观察信号复制为摘要（不是原文答案），每条绑定
source_id、适用范围和检查方式。官方文件说“仅供参考”时保留该标签。

## 典型拆法

- 机理题：几何/状态定义 → 控制方程 → 参数辨识 → 离散求解 → 工程指标；
- 离散题：实例/状态 → 目标约束 → 小规模精确基线 → 大规模算法 → 具体方案；
- 数据题：数据契约 → 探索/检验 → 定量模型 → 预测/决策 → 误差和方案；
- 在线题：时刻 t 的信息集 → 策略 → 状态更新 → 多情景评估；
- 开放题：主体/目标 → 可行性和经济性 → 数据收集 → 风险边界。

## 硬门

- 任一小问没有 deliverable 或 evidence expectation：BLOCKED；
- DAG 有环或依赖未来信息：BLOCKED；
- 把背景描述当约束，或把团队偏好当目标：需退回 scope；
- 只列算法不列输入输出/单位：不得进入 model-routing；
- 未登记开放问和“讨论/改进”要求：coverage 失败。

## 交付模板

~~~yaml
id: Q2
prompt_ref: file:problem.pdf#page=2
objective_kind: decision
inputs: [data:orders, state:inventory]
outputs: [result:weekly-plan, figure:tradeoff]
hard_constraints: [constraint:capacity, constraint:integer]
dependencies: [Q1, data-audit]
baseline: method:transparent-baseline
primary_candidates: [method:milp, method:dynamic-programming]
validation: [feasibility, baseline-gap, sensitivity]
status: PRODUCED
~~~

详细字段读取 references/artifact-contracts.md 和 references/cumcm-review-rubric.md。
