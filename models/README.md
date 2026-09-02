# 校赛 B 题求解器

`solve_b_problem.py` 是题目《电信客户流失分析与挽留策略》的可复算入口。它只读取命令行给出的附件，不把原始客户表复制到仓库；输出目录中的 `risk_scores_local.csv` 含客户编码，只应留在 Owner 的本地运行目录。

## 运行

在拥有附件的机器上安装 `requirements-b.txt` 后执行：

```powershell
python -X utf8 models/solve_b_problem.py `
  --input "C:\path\校赛B题附件.csv" `
  --output runtime/solo-test/b_solution `
  --seed 42
```

编码自动尝试 `utf-8-sig`、`gb18030`、`gbk` 和 `utf-16`。本次附件实际识别为 `gb18030`，7043 行、21 列，11 个在网 0 个月的空总费用按题意口径置为 0。

## 方法与输出

* Q1：逐字段列联表检验、修正后的 Cramér's V、分组流失率和交叉群体流失率；这些是关联证据，不是因果效应。
* Q2：参考编码的 Logistic 回归（数值变量标准化、类别变量 one-hot 且丢弃第一水平）作为可解释判别器；五折 OOF 概率用于校准与策略评估；HistGradientBoosting 作为非线性基准。
* Q3：对每个客户使用 `p q L-C` 的期望净收益判据，其中 `C=150` 元、`q=0.35`、`L=2000` 元，得到 `p\ge C/(qL)=0.2142857`；同时输出固定预算的风险排序和参数敏感性。
* Q4：把竞争降价、宏观下行和复合压力写成显式 log-odds 扰动情景；扰动幅度、成功率和成本都是压力假设，不能解释成从横截面数据估出的价格弹性。输出逐情景正收益集合、稳健排序和合同分层结果。

主要文件：

| 文件 | 含义 |
|---|---|
| `data_quality.json` | 行列、重复、缺失、取值域和目标分布 |
| `associations.csv` / `group_rates.csv` / `intersection_rates.csv` | Q1 关联、分组与交叉群体统计 |
| `model_metrics.json` / `calibration.csv` | Q2 留出、五折和 OOF 指标 |
| `feature_effects.csv` | 参考类别下的 Logistic 系数与优势比 |
| `policy_comparison.csv` / `policy_sensitivity.csv` | Q3 经济策略 |
| `scenario_summary.csv` / `scenario_segments.csv` / `robust_policy.csv` | Q4 压力、分层与稳健策略 |
| `risk_scores_local.csv` | 本地运营用客户级 OOF 风险，不进入版本库 |
| `fig_*.png` | 论文图表 |

`paper/evidence/artifact_manifest.json` 和 `validation_results.json` 分别登记文件哈希/依赖与可复现检查；两者不包含客户编码。

## 解释边界

模型预测的是观测关联风险；没有随机挽留实验，不能声称某一优惠对某个客户的个体 uplift。Q4 没有竞争价格、宏观变量或时间序列，因此只做可审计的压力测试。部署前应以新一期带标签数据做时间切分回测，并用随机对照实验重新估计 `q`。
