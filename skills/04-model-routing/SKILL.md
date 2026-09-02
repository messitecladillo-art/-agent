---
name: 04-model-routing
description: 根据小问的数学结构、数据证据和约束选择透明基线、主模型与备用模型，并记录适用域、禁用条件、假设和验证；用于防止算法堆砌和关键词套模。
---

# 模型路由与方法卡

本技能只做有理由的模型决策，不把资料目录、论文出现次数或语言模型偏好当作适用性
证明。它应该让审稿人能回答：为什么这个模型解决这个小问，为什么没选另一个。

## 输入

- problem-contract 和 question DAG；
- data-contract、字段/单位/时间粒度及缺失/泄漏报告；
- 题型 review signals；
- 可用方法卡、软件/计算预算和截止时间。

## 输出

每个小问一份 model-contract：

- target_kind、baseline、primary、fallback；
- objective、decision/state/response variables；
- assumptions、constraints、parameter ranges；
- method applicability、prohibitions、complexity；
- 选择/放弃理由及新增价值；
- 算法参数、停止条件和验证计划；
- 到 derivation、solver、writing 的 typed interfaces。

## 决策顺序

1. 先写题面目标和可计算输出，禁止先列模型名；
2. 判断连续/离散、确定/随机、离线/在线、静态/动态、单/多主体；
3. 区分机制解释、统计关联、预测、优化、评价、仿真和证明；
4. 选最小透明 baseline，写其可解释范围和不足；
5. 选择一个主模型，最多保留必要备选；每个复杂组件写“删掉后的差异”；
6. 检查可识别性、量纲、可行域、数据量和计算时间；
7. 预注册验证，只有通过后才将 candidate 升级为 primary。

## 路由规则

- 有守恒、几何、状态转移和边界：先机制模型，再数值求解/优化；
- 有明确线性/整数结构：先 LP/MILP/网络/动态规划，再考虑启发式；
- 有时间序列：先季节朴素/指数平滑等基线，使用滚动回测；
- 有标签/连续响应：先可解释统计基线，再比较树模型/神经网络；
- 有多属性排序：先定义指标和方向，再审权重稳定性；明确机理题禁用无针对性加权；
- 有随机个体/排队：先写信息集、规则、暖机和重复，再仿真；
- 有在线决策：模型只能看当时信息，未来数据必须在契约中列为禁用。

## 方法卡最低字段

每张卡必须有 applicability、prohibitions、assumptions、inputs、outputs、validation、
fallback、evidence_refs 和 compatible_block_kinds。evidence_refs 指向资料观察或方法
文档，只证明“候选依据”，不证明当前题目适用。

## 反堆砌检查

若出现多个算法并列跑一遍，必须回答：

- 共同目标和同一数据切分是否一致；
- 比较指标是否预先冻结；
- 是否存在更简单但同样有效的路线；
- 结果差异对应什么机制/假设；
- 是否有消融、重复或小规模精确对照；
- 失败的方法是否仍保留失败原因。

答不上来就删除多余方法，而不是继续加模型。

## 题型最低交付

### 机理/连续

方程、参数来源、初值/边界、离散方案、守恒/收敛验证。

### 离散/优化

变量、目标、硬约束、可行解修复、精确小规模基线、gap/终止和具体方案。

### 数据/预测

响应和特征定义、切分、变换、误差/区间、时间效应、残差与外推边界。

### 仿真/策略

信息集、状态、动作、随机源、重复次数、暖机、置信区间和策略比较。

## 硬门

- 没有 baseline：BLOCKED；
- 没有适用域或禁用条件：BLOCKED；
- 主模型依赖未验证字段/参数：CANDIDATE；
- 把相关/特征重要性写成因果：BLOCKED；
- 启发式无可行性或重复测试：UNVERIFIED；
- 选择理由只有“精度更高/论文常用”：退回重做。

按需读取 references/method-routing-matrix.md、references/cumcm-review-rubric.md 和
references/artifact-contracts.md。
