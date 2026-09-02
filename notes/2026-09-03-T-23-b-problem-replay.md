# T-23 按 Skill v2 重做校赛 B 题

## 状态与范围

- 状态：READY_FOR_REVIEW。本轮已完成可复算重跑、证据契约、论文渲染和回归门，但仍等待 Owner 审阅后才适合投稿。
- 目标：在 T-22 资料驱动 Skill Registry v2 并入工程后，用同一套固定链重新处理用户提供的校赛 B 题，不把 T-21 的旧汇总结果直接当作新结果。
- 工作方式：按 Owner 此前的“暂时不用别的 agent”要求由 Codex 单 Agent 执行。Scope、Producer、Critic、Challenger、Auditor 是工作区内的显式阶段，不冒充 Claude、Antigravity 或其他外部 Agent 已独立签字，也没有声称跨工具会话已同步。
- 安全边界：原始 DOCX/CSV 只读、只以哈希和结构引用锁定；客户级 risk_scores_local.csv 仅保留在本机运行目录，不进入 Git 证据包；未执行资料包或附件中的未知代码。

## 输入与版本锁定

| 输入/版本 | 记录 |
|---|---|
| 题面 | 校赛B题.docx；SHA-256 c2049336b8ef6d85ba5d52fc943d9deb839e8a4a20d083807cc7b267a0c96c89 |
| 数据 | 校赛B题附件.csv；SHA-256 7131cd7542bc248f090e26e1beb40d22b9e9f1ec32d8c8854d71377a94b8d858；编码 gb18030 |
| 数据规模 | 7043 行、21 列；流失 1869、留存 5174、流失率 0.2653698708；重复行/重复客户编码均为 0 |
| 缺失审计 | 11 个总费用空值全部对应在网时长 0 月，按结构性零处理；剩余缺失为 0 |
| 输入 revision | manifest:f262819cfcab8f94d70ac27648b7bdde688d133867760acf47020b9419 |
| Skill Registry revision | skill:3d5f0dd4b8bbe91925aca161ff76bb5d5f847516108bcfa1cce91d99dce3bd4e |
| 资料源 manifest | a3eb5ea717a45dee3b280afc506b37df3026e7142a9f3411e5bdafe3bc4306a |
| 结果摘要 hash | sha256:2d961aee1e60267faf6e184eec7a02397a80c57ff6a63f70399f0bf7d54da858 |
| 求解/论文代码 revision | ee9883392060644c5be12adb0357fd94560fde94 |
| 证据包 revision | 5f32313（本笔记更新提交后以 git log 为准） |

题面结构抽取到 Q1（群体与因素关系）、Q2（流失判定）、Q3（成本/成功率/损失下的挽留策略）、Q4（竞争和宏观冲击下的稳健性与动态调整）。DOCX 结构抽取通过（13 段、12 段非空、0 表格）；当前 Windows 环境没有 LibreOffice，因此题面页面级视觉检查标为 PENDING，没有把结构抽取冒充版式检查。

## 按四问重建的路线

1. **Q1 关联画像**：对 16 个类别字段做列联表、卡方、修正 Cramér V、BH-FDR，并报告数值字段 Mann--Whitney 效应、群体分母和 Wilson 区间；交叉画像只描述条件关联，不写成因果。
2. **Q2 判定方法**：保留多数类和题面核心字段 Logistic 作为基线，主路由为参考类别编码的全画像正则化 Logistic；预处理在每个分层折内拟合，使用固定 20% 留出、3 次重复 5 折 OOF、500 次 bootstrap、固定/分位数校准和结构零/中位数消融。
3. **Q3 挽留策略**：由 g_i=p_i q L-C 做单位检查和逐人经济决策。题面 C=150、q=0.35、L=2000 导出 tau=C/(qL)=0.2142857；同时比较不干预、全员、经济阈值和 Top-k 容量策略，并用独立算术实现复核。
4. **Q4 压力与稳健性**：没有竞争价格/宏观时间序列时，不拟合虚假的外部弹性；对 log-odds 施加声明区间，做 256 点 LHS（seed=446），再加入由单调性证明的精确最坏角点 u=m=0,q=0.25,C=180,L=1800。逐人取跨情景净收益下界并给出反例阈值和动态触发规则。

## 主要结果

### Q1

- 最大观测关联效应为合同类型 V=0.4098，其后为在线安全 0.3470、技术支持 0.3425、互联网服务 0.3220。
- 所有表格同时保留样本量、流失率、区间和多重比较校正；结论类别为 OBSERVED，不能解释为干预因果。

### Q2

- 全画像 Logistic 重复 OOF ROC-AUC 0.8451197420，AP 0.6531340221，Brier 0.1354992911，Log loss 0.4173586714。
- 5 折均值 AUC 0.8450814579，折间标准差 0.0115717199；500 次 bootstrap ROC-AUC 95% 区间 [0.8352758011, 0.8550617514]。
- 固定 20% 留出 AUC 0.8421710713。核心字段 Logistic OOF AUC 0.8358601668，因此完整画像的增量是可量化的，不只凭模型名称判断。
- OOF 固定箱 ECE 0.0129771090，分位箱 ECE 0.0127263331；最大固定箱偏差 0.1068419217，故不宣称“完美校准”。
- 结构性空值置零与中位数对照的 AUC 差约 1.16e-4，没有把 11 个空值处理选择夸大成主要结论。

### Q3

- 经济阈值 0.2142857143；OOF 阈值策略选 3281 人（约 46.61%），独立算术复核的期望净收益 628279.0392677826 元。
- 复核人数为 3281，独立计算与主计算收益差小于 3e-10 元；阈值策略 bootstrap 95% 区间为 [608542.7360,651432.4314] 元。
- Top-10% 和 Top-20% 期望净收益分别约 250862.17 元和 437095.34 元，并提供 bootstrap 区间。所有金额是题面平均成功率下的期望值，不是已实现利润或个体 uplift。

### Q4

- 声明压力盒：竞争 logit 扰动 [0,0.5]、宏观扰动 [0,0.3]、成功率 [0.25,0.35]、成本 [150,180]、损失 [1800,2200]，合同乘数和短在网修正均在结果 JSON 中登记。
- 只用 LHS 时曾得到 2420 人；红队检查发现抽样不能保证覆盖最坏角点。修正后显式加入精确角点，稳健正收益集合降为 **2105 人（29.8878%）**，逐人最坏下界和 **182898.4389863646 元**。
- 全体客户最小逐人下界 -179.4361 元，中位数 -93.3178 元；最不利角点的基础风险边界约 0.4。这组数字只对声明压力盒成立，属于 HYPOTHESIS，不是市场事实。

## 交付物

- 求解器：[models/solve_b_problem_v2.py](../models/solve_b_problem_v2.py)
- 证据构建器：[scripts/build_b_replay_artifacts.py](../scripts/build_b_replay_artifacts.py)
- 论文源：[paper/b_problem_solution_v2.tex](../paper/b_problem_solution_v2.tex)
- 论文 PDF：[paper/b_problem_solution_v2.pdf](../paper/b_problem_solution_v2.pdf)，11 页 A4
- 渲染登记：[paper/render_qa_v2.json](../paper/render_qa_v2.json)
- 聚合证据根目录：[artifacts/runs/T-23-b-problem-v2/](../artifacts/runs/T-23-b-problem-v2/)
  - input-manifest.json、problem-contract.json、question-map.json
  - data-contract.json、derivation-registry.json、model_route.json
  - results/summary_v2.json、Q1--Q4 聚合 CSV/JSON/PNG
  - validation-report.json、run-manifest.json、paper-contract-v2.json
  - assembly.json、artifact-manifest.json、脱敏 solver 日志

## 已执行门禁

| 门 | 结果 |
|---|---|
| data contract strict | PASS，21 字段、7043/21、重复 0、无泄漏契约 |
| run manifest strict | PASS，exit 0，23 个安全聚合/论文产物 |
| paper contract strict | PASS，6 variables、3 equations、4 claims、4 crossrefs、12 checks |
| LaTeX 数学审计 | PASS，33 labels、4 refs、24 environments、0 error/warning |
| XeLaTeX | 两遍 exit 0；11 页 A4；无 Overfull/Underfull、未定义引用或裁切 |
| PDF 视觉 QA | 11/11 页 PNG；重点页、表格、公式、四张图均检查；Q4 图含精确最坏角点 |
| workflow assembly strict | PASS，12 节点、22 边、无缺少必需块 |
| Skill Registry strict | PASS，16 entries（13 skills/3 workflows/12 sources） |
| Skill regression | 27/27；backend 158 passed；Node 两入口语法通过；compileall 通过 |

## 尚未关闭的门

1. 校赛当届官方论文模板、匿名规则、页数上限尚未随输入提供；当前 PDF 是“内部复核稿”，不能直接称为官方投稿格式。
2. 数据是横截面，没有时间回测、随机挽留标签、竞争价格或宏观序列；Q1/Q2 是关联预测，Q3 使用题面平均参数，Q4 是假设边界。
3. “独立复现”仅指新求解器重跑加 Q3 独立算术核对，不是第二套模型实现；没有 Claude/Antigravity 的独立签字。
4. 后续若补充月份、触达、优惠和成本记录，应按 D1--D4 规则重做时间切分、校准和随机对照实验，不得沿用本次静态压力盒作为事实。

## 下一步

- Owner 先审阅 Q4 的压力区间和 2105 人安全边界，再决定是否采用；
- 补齐官方格式后重新编译并做投稿版匿名/页数检查；
- 若要启用多 Agent 交叉评审，再按 multi-agent-collaboration 协议发出带 revision、哈希、证据引用和过期时间的只读评审包。
