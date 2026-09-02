---
name: workflows-diy-puzzle
description: 让使用者以拼图方式自由装配数学建模步骤和方法卡，同时自动检查端口、依赖、证据链与发布硬门；适用于探索路线和非标准题型。
---

# DIY 拼图装配流程

DIY 的自由度体现在选择路线，不体现在删除证据。先建立最小骨架，再按需要插入方法。

## 最小骨架

scope → questions → baseline → validation → writing → release

data、contract、mechanism、optimization、simulation、sensitivity、challenge、defense
按题面插入。没有数据时可把 data 标记为 not-applicable，但要写理由；没有机制时不能
伪造 mechanism。

## 每块配置

- block_id、kind、input_ports、output_ports；
- method_id（可空；baseline 块不可空）；
- question_ids 和适用范围；
- owner/write boundary；
- assumptions、prohibitions、validation；
- source_refs、skill_refs 和 capability revision。

## 装配动作

1. 从题型或空白画布建立 scope/questions；
2. 为每个小问插入透明 baseline；
3. 连接端口并检查类型；
4. 为主路线插入一个或多个候选方法；
5. 对每个候选填写适用/禁用/假设/验证；
6. 插入 challenge、sensitivity 或独立复算；
7. 连接 claim evidence 到 writing；
8. 生成 assembly diff 和 validation report；
9. 只有 release 门通过才提交。

## 自动拒绝

- 端口类型不匹配；
- 环；
- 小问没有输出；
- baseline、validation 或 claim evidence 缺失；
- 方法没有 fallback/禁用条件；
- revision 不一致；
- 以创新卡或资料命中替代验证。

## 创新记录

创新卡必须写 baseline、difference、necessity、boundary、validation。它是待审假设，
不是“创新已成立”的标签。

## 端口与状态的细则

### 端口兼容

端口类型是严格的语义类型，不是仅供 UI 展示的字符串。连接前逐项检查：

- `problem_contract → subproblems`：题面 revision 必须一致；
- `data_contract → model/feature`：字段、单位、时间窗和泄漏报告必须已冻结；
- `mechanism_spec/model_contract → solver`：初值、边界、参数域和约束齐全；
- `result → validation`：结果必须带 run_id、退出码和 artifact hash；
- `validation_report → writing/release`：报告状态至少为 `READY_FOR_REVIEW`，P0/P1 已处理；
- `paper_claims → release_pack`：每个 claim 都有 evidence_ref，未验证项不能进入摘要/结论。

若一个块同时输出多个同名语义量，必须使用不同的 `port_id` 或显式转换块，禁止
靠位置猜测。转换块要记录原类型、目标类型、换算公式、单位和误差。

### 可保存与可提交是两种动作

- `SAVE_DRAFT`：允许缺块、缺方法或有未决项，但必须保存当前 assembly revision、
  缺口和下一动作；不能标成可发布。
- `SUBMIT_REVIEW`：必需块、端口、DAG、revision、证据和验证字段全部通过；进入
  独立审查队列，作者不能自审自关。
- `RELEASE`：只有 Owner 在 review finding 关闭后批准，才生成不可变 release pack。

### 小问覆盖矩阵

每个拼图节点都要声明 `question_ids`。校验报告应生成矩阵：

| 小问 | 输入 | 方法块 | 输出 | 验证 | 论文位置 | 状态 |
|---|---|---|---|---|---|---|
| Q1 | … | … | … | … | §… | READY/BLOCKED |

某个小问没有输出、验证或写作映射时，即使整张图连通，也必须拒绝提交审查。

## DIY 的推荐装配策略

1. 先套用与题型最接近的 preset，保留完整硬门；
2. 逐小问替换 primary，先保留透明 baseline 作为对照；
3. 每替换一个块就运行一次结构校验并记录 diff，不要最后一次性排错；
4. 用一个独立 review/反例块挑战新方法，再决定是否保留；
5. 若新方法没有可量化增益、可解释差异或可复现验证，撤回到 baseline；
6. 把最终拼图导出为 `assembly`、`method_binding`、`coverage_matrix` 和 `innovation_card`，
   供固定流程的论文与发布门继续使用。

DIY 不等于绕过流程：它改变的是“哪一个候选方法接在哪一块”，不改变证据、权限、
版本和 Owner 审批协议。
