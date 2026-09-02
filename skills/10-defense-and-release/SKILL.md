---
name: 10-defense-and-release
description: 将已验证的模型与论文整理为答辩证据包和提交前发布清单，检查题面覆盖、匿名、版权、格式、复现和风险披露；适用于最终交付，不负责替换未验证结果。
---

# 答辩与发布门

本技能把评委可能追问的“为什么这样建模、数字从哪来、何时失效”变成证据卡，并在
不可逆提交前执行最后一道门。发布不是把状态改成绿色，而是冻结 revision 后的审计结果。

## 输入

- frozen problem/model/data/equation/claim registries；
- validation、red-team、render QA 和官方 format profile；
- 论文 PDF/DOCX、代码、结果、引用和匿名信息；
- 当届提交通知及 Owner 的发布授权。

## 输出

- defense-question-matrix；
- evidence pack（来源、命令、hash、限制和负责人）；
- release-checklist；
- review report、未决风险和 rollback 包；
- RELEASED 或 BLOCKED 状态，不得模糊化。

## 答辩问题矩阵

至少覆盖：

1. 每个小问究竟回答了哪个量/方案？
2. 为什么选 primary，baseline/fallback 是什么？
3. 每个关键假设的依据、适用范围和放松后变化？
4. 参数来自题面、数据估计还是假设？是否可识别？
5. 结果如何验证，约束/守恒/误差是否满足？
6. 灵敏度或反例是否会翻转结论？
7. 哪些数字可复现，命令、版本、hash 在哪里？
8. 哪些结论不能推广，下一步需要什么数据？
9. 论文和范文/资料的原创与引用边界？
10. 竞赛规则、匿名、页数和格式依据是什么？

每张回答卡同时写“短答、证据 ref、限制、若被反驳的诚实回应”。

## 发布顺序

1. 冻结输入、代码和能力 registry；
2. 重新生成所有结果和摘要 claim；
3. 运行结构/数学/数据/验证/渲染/版权/匿名检查；
4. 清理占位符、个人信息、调试输出和未授权附件；
5. 由非作者复核关键数字和 PDF 页面；
6. 生成包含 manifest、环境、命令、日志和回滚指针的发布包；
7. Owner 明确批准外部/不可逆提交后才执行提交。

## 硬阻塞

- P0/P1 finding 未关闭；
- 未验证数字进入摘要/结论；
- 题面小问或交付物缺失；
- 公式/图表/引用断链或渲染缺陷；
- 匿名/页数/当届规则未确认；
- 版权、敏感数据或外部发布授权不清；
- 发布包不能在干净环境复现。

## 失败与回滚

任何门失败都保留旧 RELEASED 包，当前 revision 标 BLOCKED；修复必须产生新 revision，
不能覆盖旧日志。外部提交、推送或删除属于额外动作，必须有用户/Owner 授权。

按需读取 references/evidence-and-status.md、references/artifact-contracts.md 和
references/paper-layout-profiles.md。
