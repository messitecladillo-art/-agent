---
name: 05-mathematical-derivation
description: 把每个小问组织成定义—假设—变量—方程—推导—离散/算法—判据—解释的数学链；适用于论文主体、模型审查和需要严谨数学语言的任何建模任务。
---

# 数学推导与模型表达

本技能是新体系的核心质量门。它不替代模型选择或求解器，而是阻止“模型名直接跳到
数字”，让读者能逐行复核逻辑、单位和适用边界。

## 输入与输出

输入：problem-contract、question DAG、data/model contract、假设和参数来源。

输出：

- variable_registry 与 assumption_registry；
- equation_registry（语义 ID、输入输出、域、单位、验证）；
- model-to-algorithm map；
- 每个小问的 derivation card；
- 可供论文和代码共享的符号/单位/结果接口；
- 未完成推导和不可识别参数清单。

## 每个小问的固定链

题面目标
→ 观测量/决策变量
→ 符号、单位、方向和粒度
→ 假设与理由、适用域和禁用条件
→ 定义、目标函数、约束或控制方程
→ 中间量、代数变形、初值/边界/接口
→ 离散格式、算法、停止/稳定条件
→ 结果、区间、题意翻译
→ 验证、敏感性、反例和限制。

## 变量规则

新符号首次出现时同时说明含义、类型、单位、取值域、正负/坐标约定、时间/空间粒度和
source_ref。同一个符号不能换义；必须换义时使用显式下标或语义 ID。无量纲量也要写
“无量纲”。变量表不能代替正文首次定义。

## 假设规则

假设必须是可攻击的句子，并登记：

- statement：在什么范围把什么量怎样处理；
- reason：省略了哪一项、降低了什么复杂度；
- evidence：题面/数据/文献/经验还是暂定；
- test：残差、敏感性、边界案例、外部对比或消融；
- disable_when：何时必须关闭；
- relaxation：放松后的模型；
- status：HYPOTHESIS 或 VERIFIED。

“数据可靠”“误差很小”“忽略其他因素”若无范围和检查，视为无效假设。

## 方程规则

每条核心方程登记 id、label、question_id、role（definition/objective/constraint/
governing/discretization/criterion）、inputs、outputs、domain、assumptions、
derivation_from、unit_check 和 validation_refs。加法项、目标、约束和阈值逐项做量纲
检查；秒/小时、米/公里、百分比/小数和样本/总体不能暗中换算。

长推导按可解释中间量拆行；条件系统显式写初值/边界；线性化、截断、正则化、插值和
平滑必须说明误差或适用域。显示编号交给 LaTeX/Word 引擎，正文使用语义引用，不手写
会漂移的编号。

## 从连续到离散

必须写：

1. 网格/时间步/状态离散和索引；
2. 边界更新、初值和接口量；
3. 稳定性、收敛或停止准则；
4. 参数、容差、随机种子和复杂度；
5. 输出提取和误差传播。

算法伪代码描述输入、更新、分支、终止和输出；代码截图不能代替数学推导。

## 结果叙事

每段采用“目的句—条件句—数学句—解释句”。只有在紧邻定义可直接复核时使用“显然/
易得”。结果段必须把数学量转译成题目要求的方案、建议、范围或判断，同时写清不能
推出的结论。

## 接口硬门

- 未定义变量或换义：BLOCKED；
- 方程有未登记输入/输出：BLOCKED；
- 加法或约束量纲不一致：BLOCKED；
- 缺初值/边界/定义域：UNVERIFIED；
- 数字没有 equation/result/validation 回链：UNVERIFIED；
- 公式仅以图片或代码出现：退回补文字链。

深层模板和注册表字段读取 references/artifact-contracts.md 与 references/paper-layout-profiles.md；
需要逐段写数学叙事或处理长公式时，再读 references/derivation-and-layout-guide.md 和
skills/references/registries-and-evidence.md。
