---
name: 03-data-and-evidence
description: 为附件和外部数据建立可追溯的数据契约、字段/单位/时间粒度、缺失异常处理和无泄漏评估切分；适用于所有带数据、实验、预测或方案题。
---

# 数据与证据契约

数据处理不是模型前的清洁动作，而是会改变结论的建模步骤。原始文件只读，所有转换
都要能回放、比较和撤销。

## 输入与输出

输入：problem-contract、原始附件、外部数据授权范围、目标预测/决策窗口。

输出：

- data-contract/v2；
- data dictionary（字段语义、单位、粒度、来源和状态）；
- raw/processed/quarantine 清单及哈希；
- missingness/outlier/encoding report；
- split_spec 和 leakage report；
- 可用于 model-routing 的特征/响应候选；
- 不能解释或不能使用的字段清单。

## 逐步流程

### 1. 原始数据登记

为每个文件登记路径、类型、大小、SHA-256、编码、sheet/page、读取工具和抽取状态。
不因扩展名相信内容；抽样读取表头、行列数、日期范围和单位。损坏/乱码文件进入
quarantine，不能静默修复。

### 2. 字段语义与单位

每列写唯一 field_id、自然语言含义、kind（index/input/state/parameter/decision/label）、
单位、粒度、范围、正负方向、缺失编码和 provenance。单位转换显式写 factor 和原值；
金额、比例、角度、时间和空间尺度不可混用。

### 3. 数据质量

- 缺失：区分 MCAR/MAR/结构性缺失/不可观测；先报告模式，再选删除、插补或缺失指示；
- 异常：区分录入错误、真实极端和题面特殊值；记录规则、阈值、删除数量和保留版本；
- 重复：按实体/时间/行键检查；
- 时间：统一时区、日期粒度、排序和窗口；
- 分类：固定映射表，未知类别不强行归入已知类；
- 多表：主键、连接方向、行数变化和未匹配行都要对账。

### 4. 防泄漏切分

先冻结评估问题：预测时点、预测窗、部署主体和可见信息集。然后选择 blocked-time、
group、stratified 或 nested split。所有缩放、插补、特征选择、目标编码在训练折内拟合。
同一主体不能无意跨 train/test；在线题禁止使用未来状态。

### 5. 探索分析

探索结果只用于提出假设。按题型需要报告分布、效应量、相关方法条件、时间季节性、
分组差异、样本量和可视化；简单描述统计不能直接代替定量模型。相关不写成因果。

### 6. 形成可交接证据

processed 数据必须由脚本生成并写 manifest；每个衍生字段绑定输入字段、公式、代码、
版本和检查。将不确定字段标 CANDIDATE/UNVERIFIED，交给模型技能决定是否使用。

## 数据题特别检查

资料中的国赛评阅信号反复要求：异常/缺失/打折/退货/无销量、时间效应、关联条件、
预测精度、成本/库存和方案可行性。不要只做热力图、简单回归或一周复制策略。

## 硬门

- raw 文件被覆盖或没有 hash：BLOCKED；
- 关键字段无单位/粒度/来源：BLOCKED；
- 插补/异常处理没有敏感性或对照：UNVERIFIED；
- 测试集参与预处理/调参：BLOCKED；
- 在线题使用未来字段：BLOCKED；
- 外部数据没有授权和时间截点：BLOCKED。

运行结构校验：

~~~powershell
python -X utf8 skills/03-data-and-evidence/scripts/validate_data_contract.py data-contract.json --strict
~~~

详细 schema 和方法边界读取 references/artifact-contracts.md、references/evidence-and-status.md。
