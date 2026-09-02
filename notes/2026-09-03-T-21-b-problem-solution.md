# T-21 校赛 B 题完整求解与论文交付

## 状态

- 状态：`READY_FOR_REVIEW`（已完成可复算产出，等待 Owner/独立评审确认后再进入 `main`）。
- 分支：`task/T-21-solve-b-problem`。
- 工作方式：本轮按 Owner 要求由 Codex 单 Agent 完成；“建模者、质疑者、证据审计者”是同一工作区内的三次显式复核，不冒充外部 Agent 已独立签字。
- 原始题面和 CSV 只以哈希锁定，未复制进仓库；客户级风险文件只保存在本地 `runtime/solo-test/`。

## 输入锁定

| 输入 | 实际编码/规模 | SHA-256 |
|---|---:|---|
| `校赛B题.docx` | 题面：2026 华中师范大学数学建模竞赛 B 题 | `c2049336b8ef6d85ba5d52fc943d9deb839e8a4a20d083807cc7b267a0c96c89` |
| `校赛B题附件.csv` | `gb18030`；7043 行、21 列；字段宽度一致 | `7131cd7542bc248f090e26e1beb40d22b9e9f1ec32d8c8854d71377a94b8d858` |

题面契约识别出 Q1–Q4。解析器同时覆盖 `问题4`、`问题 4`、`Q4`，并在存在显式问题标题时不把 Q3 内的 `(1)(2)(3)` 经营信息误切成新问题。

## 建模链

1. **Q1 关联与画像**：类别字段列联表、卡方检验、修正 Cramér's V、群体/交叉群体流失率。结论仅作横截面条件关联，不写成因果。
2. **Q2 判定方法**：参考类别编码的 Logistic 回归作为可解释基线；数值字段标准化、类别字段 one-hot 丢弃第一水平；分层 20% 留出、五折 OOF 和十分位校准；HistGradientBoosting 作为非线性对照。
3. **Q3 挽留策略**：以 `$g_i=p_iqL-C$` 为单客期望净收益，题面参数 `$C=150$`、`$q=0.35$`、`$L=2000$`，得到阈值 `$p_i\ge C/(qL)=0.2142857$`；同时输出全员、阈值、Top-k 和参数扫描。
4. **Q4 稳健性**：将竞争降价、宏观下行、复合压力写成显式 log-odds 扰动，并同步改变成本/成功率；以跨情景逐人净收益最小值构造保守排序。外部冲击幅度不是从本附件识别出的价格弹性，保持 `HYPOTHESIS`。

## 关键结果

- 目标流失率：`0.2653699`（流失 1869、留存 5174）；重复行和重复客户编码均为 0；总费用有 11 个结构性空值，按在网 0 月规则置 0。
- Q1 最大关联强度：合同类型 Cramér's V=`0.4098`；在线安全=`0.3470`；技术支持=`0.3425`；互联网服务=`0.3220`。代表性交叉群体“月付+光纤+电子支票+在网不超过 6 月”流失率=`75.45%`（n=440）。
- Q2 Logistic：留出 ROC-AUC=`0.842171`、AP=`0.634903`、Brier=`0.137984`；五折 AUC 均值=`0.845033`、标准差=`0.013521`；OOF AUC=`0.845001`、Brier=`0.135571`。HGB 留出 AUC=`0.837978`，作为非线性对照。
- Q3 OOF 阈值策略：选择 3286 人（46.66%），观测流失率=`48.23%`，期望净收益=`630184.63` 元；全员干预期望净收益=`253276.19` 元。该排序使用平均成功率，不是个体 uplift。
- Q4 复合压力：预测流失率=`33.89%`，正收益人数=`3252`；稳健正收益集合 3122 人，逐人最坏净收益下界和=`506335.09` 元。该结果依赖显式压力假设。

## 交付物

- 求解器：[models/solve_b_problem.py](../models/solve_b_problem.py)
- 论文源文件：[paper/b_problem_solution.tex](../paper/b_problem_solution.tex)
- 编译 PDF：[paper/b_problem_solution.pdf](../paper/b_problem_solution.pdf)，12 页 A4
- 题面/模型契约：[paper/b_problem_contract.json](../paper/b_problem_contract.json)
- 聚合证据：`paper/evidence/`（数据质量、关联、交叉群体、模型指标、校准、策略、情景和稳健排序）
- 证据登记：[paper/evidence/artifact_manifest.json](../paper/evidence/artifact_manifest.json)
- 验证登记：[paper/evidence/validation_results.json](../paper/evidence/validation_results.json)
- 渲染登记：[paper/evidence/render_qa.json](../paper/evidence/render_qa.json)

## 已执行验证

| 检查 | 命令/证据 | 结果 |
|---|---|---|
| 求解器 clean-run | `python -X utf8 models/solve_b_problem.py --input "C:\\Users\\zyy20\\Downloads\\校赛B题附件.csv" --output runtime/solo-test/b_solution_final --seed 42` | exit 0，返回 `PASS`；聚合文件与仓库证据逐项相同 |
| 题面/契约审计 | `audit_paper_contract.py paper/b_problem_contract.json --strict --json` | `PASS`；14 variables、11 equations、10 claims、14 crossrefs、8 checks |
| LaTeX 数学审计 | `audit_latex_math.py paper/b_problem_solution.tex --release --json` | `PASS`；36 labels、20 refs、0 errors、0 warnings |
| XeLaTeX 双遍 | `xelatex ... paper/b_problem_solution.tex`（两遍） | exit 0；12 页 A4；无未定义引用、缺字或 Overfull；1 条非阻断 Underfull hbox |
| PDF 视觉 | `pdfinfo` + `pdftoppm`，12 页逐页检查 | 页面边界、公式、表格、图形均可读；无裁切 |
| 服务端 E2E | `python -X utf8 runtime/solo-test/api_e2e_t21.py` | `PASS`；健康、Q1–Q4 契约、能力目录、知识检索、路由预览、拼图组合、LaTeX job 全通过 |
| 后端回归 | `python -m pytest backend -q --basetemp .pytest-tmp-T21` | `153 passed` |

E2E 摘要保存在本机忽略目录 `runtime/solo-test/api_e2e_t21.json`，只含计数、revision 和 PDF 哈希，不含客户编码或客户级预测。

## 本轮代码增量

- `backend/problem_contract.py`：识别带空格的阿拉伯数字问题标题；显式标题优先，避免把括号子项切成顶层问题。
- `backend/app.py`：能力建议增加可解释的中文/英文领域别名扩展（如流失、Logistic、阈值、压力测试），并返回 `matching` 说明；方法候选返回 `matched_terms`。
- `backend/test_problem_contract.py`、`backend/test_capability_api.py`：新增上述两类回归测试。

## 尚未关闭的门

1. 未提供校赛官方论文模板、匿名规则和页数要求；当前 PDF 明确标为校赛内部复核版，不能直接宣称投稿格式合规。
2. 附件是横截面数据，没有竞争价格、宏观变量、时间序列或随机挽留实验；Q1/Q2 系数是关联解释，Q3 成功率是题面平均值，Q4 是压力假设。
3. 尚未由不同身份的 Claude/Antigravity/Owner 完成独立数学复算和最终发布审批；因此任务保持 `READY_FOR_REVIEW`，不自动合并或推送到 `main`。
