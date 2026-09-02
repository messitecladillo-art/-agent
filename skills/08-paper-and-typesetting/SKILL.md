---
name: 08-paper-and-typesetting
description: 将已验证的数学链和结果写成可读、可复核、可编译的国赛/美赛/其他赛事论文，并审计公式、图表、三线表、交叉引用、字体、页数和 PDF 渲染。
---

# 论文、数学排版与发布前渲染

本技能吸收资料包中的国赛 Word 模板、排版注意事项、美赛模板和范文结构，但把“观察到
的好版式”与“当届官方硬规则”严格分开。它不允许用模板示例文字或一篇范文填充当前题目。

## 前置条件

必须已有 problem-contract、paper profile、variable/equation registry、validation
report、claim matrix 和 artifact manifest。缺任何一项，先输出 BLOCKED/UNVERIFIED。

## 论文数学叙事

每个小问单独形成：

题面目标 → 定义/变量 → 假设与理由 → 模型/方程 → 推导 → 算法与参数 →
结果与单位 → 题意解释 → 验证/敏感性 → 限制。

摘要最后写，按开头、逐小问、结尾组织；每个关键结果绑定 claim_id。问题重述用自己的
话压缩，不能整段复制题面；问题分析不提前泄漏结果；结论必须给出可执行的方案或判断。

## 国赛排版 profile

从资料可迁移：标题/摘要/关键词集中；标题层级通常不超过三级；中文与英文/数学/代码
字体职责分明；版面紧凑；三线表；表题在上、图题在下；重要公式解释变量并编号；最终
提交 PDF。A4、具体字号、页边距、匿名字段、承诺书、页数和当前格式必须读当届官方文件，
未确认标 OFFICIAL_PENDING。

## 美赛 profile

美赛完整正文没有统一官方模板；Summary/Summary Sheet 是初筛入口。根据题目需要加入
Letter/Memo、Introduction、Models、Results、Strengths and Weaknesses 等。英文保持
术语/符号一致、短段主动语态、假设逐条论证；页数、队号、匿名和提交时间按当届规则。

## 共享结构源

problem/data/model/equation/claim/crossref/artifact 注册表是唯一内容源：

结构化源 → LaTeX → PDF、log、render QA
结构化源 → Word/OMML → DOCX/PDF、render QA

Word 公式必须可编辑，表格不用空格对齐；LaTeX 使用语义 label 和引擎编号。两种输出
不得分别手改数字、图题、公式编号。

## 图表与公式门

每个图/表/公式/算法需唯一 label、caption、范围、单位、generator、source artifact、
cited_by 和 status。图表不是装饰；caption 要让脱离正文的读者知道对象、样本/时间范围
和结论边界。公式前后有文字，长式拆成可解释步骤，变量首次出现即定义。

## 发布前审计

至少检查：

- 小问覆盖和摘要数字一致；
- 公式 label 唯一、引用可解析、无手写漂移编号；
- 单位/符号/有效位一致；
- 表题图题位置、三线表、图例、脚注和灰度可读；
- PDF 无缺字、字体回退、溢出、裁切、错误分页、空白断层；
- 代码附录可定位、入口/依赖/命令可重跑；
- 参考文献逐条引用，范文没有被复制；
- 匿名、页数和官方 profile 状态已确认。

运行结构审计：

~~~powershell
python -X utf8 skills/08-paper-and-typesetting/scripts/audit_latex_math.py paper --release --json
python -X utf8 skills/08-paper-and-typesetting/scripts/audit_paper_contract.py paper-contract.json --strict --json
~~~

结构脚本只证明结构，不证明数学正确；必须先有独立验证和 Owner 审批。

按需读取 references/paper-layout-profiles.md、references/artifact-contracts.md 和
references/cumcm-review-rubric.md；数学推导细节读取
skills/05-mathematical-derivation/references/derivation-and-layout-guide.md。完成修改后，
可运行 evals/run_eval.py 检查结构正反例，不能把夹具通过当作真实论文通过。
