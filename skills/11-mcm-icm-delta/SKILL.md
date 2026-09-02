---
name: 11-mcm-icm-delta
description: 在通用数学建模链上叠加 MCM/ICM 的英文写作、Summary Sheet、Letter/Memo、Strengths and Weaknesses 与提交约束；只在赛事确认为美赛时使用。
---

# MCM/ICM 赛事增量

本技能只保存相对通用建模流程的增量，不能把美赛经验套回国赛，也不能用历史模板代替
当届 COMAP 规则。

## 前置锁定

先由 scope-lock 确认 MCM/ICM、年份、题号、队号、官方题面、页数和提交规则。缺当届规则
时，所有页数、匿名、队号和截止时间字段标 OFFICIAL_PENDING。

## 必交叙事

Summary/Summary Sheet 是初筛入口，独立写清：

- 用自己的话重述问题；
- 关键假设与理由；
- 主要变量和模型设计；
- 检验、敏感性和不确定性；
- 关键数值和可执行建议；
- strengths、weaknesses、适用边界。

不要只列技术名词或从 First we 开始流水账；第一段要让非作者迅速知道贡献和结果。

按题目需要加入 Letter/Memo，写给指定的非专业对象，说明建议、代价和风险。

## 英文数学表达

- 术语和符号前后一致，首次使用即定义；
- 以 we 和主动语态为主，短句短段；
- 现在时叙述模型，结果用准确时态；
- 公式前后有文字，避免无解释的大段推导；
- 每个 if 对应 then 或清晰条件；
- 美式拼写、主谓一致、that/which、冠词和数字格式复核；
- 不夸大、不用感叹号、不过度外推。

## 题型增量

- A：物理/连续模型、模糊目标的精确定义和数据讨论；
- B：组合优化、随机/离散仿真、足够重复和伪代码；
- C：领域知识与数据融合、度量指标、网络/动力模型和敏感性；
- D：静态网络、行为规则、多主体动态仿真；
- E：先定义 sustainability，再量化指标与多年方案；
- F：政策、伦理、利益相关者和反事实边界单独呈现。

## 硬门

- Summary 未覆盖所有子问题：BLOCKED；
- 公式变量/图表/引用未定义：BLOCKED；
- 使用未来信息或不符合赛中交流规则：BLOCKED；
- 页数/队号/截止时间未从当届规则确认：OFFICIAL_PENDING；
- 只把英文翻译当作美赛适配：退回补模型与证据链。

按需读取 references/paper-layout-profiles.md 与 references/cumcm-review-rubric.md。
