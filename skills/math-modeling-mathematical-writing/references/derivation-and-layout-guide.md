# 数学推导与排版指南

本指南是 `math-modeling-mathematical-writing` 的深层参考。先读 Skill 入口，只有在
需要起草公式、搭建论文源文件或做版式审计时才加载本文件。

## 1. 一条可审计的数学叙事

对每一个子问题建立一张“推导卡”，顺序可按题面调整，但依赖关系不能反转：

```text
Q-id / 题面目标
  ↓
观测量、决策变量、输出指标（含单位和范围）
  ↓
假设、正负号/坐标约定、数据来源与适用域
  ↓
定义、目标函数、约束或控制方程
  ↓
中间量、代数变形、边界/初值、近似误差
  ↓
离散格式/求解器/停止条件/复杂度
  ↓
结果、区间、不确定性和题目语义翻译
  ↓
验证、敏感性、失效边界、可推广方向
```

### 1.1 段落模板

每段优先采用四句结构，避免公式孤立：

1. **目的句**：说明本步解决题面中的哪一个关系或决策。
2. **条件句**：列出使用的定义、假设、数据范围或边界。
3. **数学句**：给出最小足够的公式/算法步骤，并使用语义 label。
4. **解释句**：逐项解释输入、输出、单位、方向和下一步接口；若是结果，说明能/不能推出什么。

“显然、易得、容易看出”只有在读者能从紧邻的定义或一行代数直接复核时才使用；
否则写出中间量或把论证升级为引理/命题。不要把“模型运行得到”当作推导。

### 1.2 两种证据链

| 证据链 | 适用问题 | 正文最小内容 | 不能省略 |
|---|---|---|---|
| 解析/证明链 | 极值、几何、概率推导、理论性质 | 定义、条件、引理/命题、推导、结论 | 边界情况、条件失效时的反例 |
| 数值/实证链 | 预测、优化、仿真、机制模拟 | 模型、参数/数据、算法、输出、验证 | 独立验证、误差/不确定性、复现入口 |

混合题要在接口处写清哪一量由证明得到、哪一量由计算估计；不能用一张数值表冒充
理论证明，也不能用漂亮的定理名掩盖未经验证的参数拟合。

## 2. 变量与假设登记

### 2.1 变量字段

每个变量至少登记：

| 字段 | 说明 |
|---|---|
| `id` | 稳定语义 ID，不随排版编号改变 |
| `symbol` | 正文符号；向量/矩阵/集合显式标记 |
| `meaning` | 自然语言含义，首次出现附近同步说明 |
| `kind` | `input/state/parameter/decision/output/index` |
| `unit` | SI 或题目约定；无量纲写明 |
| `domain` | 取值范围、时间/空间粒度、样本层级 |
| `sign_convention` | 正负方向、坐标原点、角度方向（适用时） |
| `source_ref` | 题面、数据列、文献、估计或假设的定位 |
| `status` | `OBSERVED/CANDIDATE/VERIFIED/UNVERIFIED` |

同一个字母若在不同子问题确实需要不同含义，应改用语义化符号或显式限定（例如
`x^{(q2)}`），不要依赖读者猜测。单位不只是表格装饰：它决定加法、比较、目标函数
和阈值是否有意义。

### 2.2 假设字段

假设写成可以被攻击的句子，而不是“数据可靠”“误差很小”这类愿望：

```yaml
- id: asm-q2-stationary
  statement: <在什么范围内，把什么量视为不变>
  reason: <为什么需要，省掉哪一项/降低何种复杂度>
  applies_to: [Q2, eq:q2-main]
  test: <可用数据、残差、敏感性或边界案例怎样检查>
  disable_when: <什么条件下必须关闭>
  relaxation: <放松后使用的备用路线>
  status: HYPOTHESIS
```

## 3. 公式组织与语义标识

### 3.1 公式前后都要有语言

```text
为回答 Q2 的资源守恒关系，令 x_t 表示 t 时刻的状态，先固定时间粒度 Δt 和边界条件。

（显示公式，label: eq:q2-balance）

式中……；左端是……，右端各项来自……。该式输出……，供下一步……使用。
```

一条关键公式的 registry 至少记录：`id`、`label`、`question_id`、`inputs`、`outputs`、
`assumptions`、`domain`、`unit_check`、`derivation_from`、`validation_refs`。显示编号由
LaTeX/Word 引擎维护，语义 ID 不因插入公式而变化。

### 3.2 长公式的分解原则

- 有共同左侧或右侧时用 `aligned`/`alignedat` 对齐等号；每行只承载一个可解释步骤。
- 条件分支用 `cases`；方程组用 `\left\{` + `aligned`，并为初值、边界、接口分组加注释。
- 超过版心的单行式优先做代换、定义中间量或拆成 (a)(b)(c)，不要缩到不可读，也不要截图。
- 无量纲化按“选择特征尺度 → 代入 → 除以基准量 → 定义无量纲群 → 解释比值”逐步展示。
- 把最终判据写成可计算的集合/不等式，并给出阈值来源（理论、数据估计或扫描），不要只写口号。

### 3.3 推荐 LaTeX 片段

以下片段是通用骨架，数字、符号和编号必须换成当前题目的真实内容。

```tex
% 导言区（按官方模板取舍）
\usepackage{amsmath,mathtools,bm,siunitx,booktabs,threeparttable}
\DeclareMathOperator*{\argmin}{arg\,min}
\newcommand{\R}{\mathbb{R}}

% 多行推导：每一行都能在 prose 中解释
\begin{align}
  y_t &= f(x_t;\theta) + \varepsilon_t, && t\in\mathcal T, \\
  \widehat{\theta} &= \argmin_{\theta\in\Theta}
    \sum_{t\in\mathcal T_{\rm train}} \ell(y_t,f(x_t;\theta)),
    && \label{eq:fit}
\end{align}

% 条件系统：域和边界条件不能藏在正文之外
\begin{equation}
\left\{
\begin{aligned}
  \mathcal F(u,\theta) &= 0, && (x,t)\in\Omega\times[0,T],\\
  u(x,0) &= u_0(x), && x\in\Omega,\\
  \mathcal B u &= g, && (x,t)\in\partial\Omega\times[0,T].
\end{aligned}
\right.
\label{eq:system}
\end{equation}

% 单位正体、变量斜体；不要把单位写成普通正文字符串
\SI{2.5}{\metre\per\second},\qquad
\Delta t\leq\frac{\Delta x}{c_{\max}}.
```

是否全局编号或按节编号由官方模板决定；示例中的 `label` 只是稳定 ID 的载体，不要
手写 `(1)`。使用 `\eqref{eq:fit}`、`\ref{fig:residual}` 等交叉引用，编译两遍并检查日志。

## 4. 模型接口、算法与验证

### 4.1 模型接口卡

```yaml
model_id: q2-primary
question_ids: [Q2]
inputs: [data:demand, param:capacity]
states: [state:inventory]
decisions: [decision:allocation]
outputs: [result:objective, result:feasibility]
constraints: [capacity, balance, nonnegative]
algorithm: <名称、版本、停止条件、复杂度>
fallback: q2-baseline
validation_refs: [val:q2-holdout, val:q2-sensitivity]
applicability: <适用域>
prohibitions: <不能外推的情形>
```

至少保留一个可解释基线，并说明主路线相对基线增加了哪一机制、数据或约束。模型堆叠
不等于创新；若增加的模块没有题面动机、消融或验证，退回审查。

### 4.2 算法叙述

正文用“输入—步骤—输出—停止条件—复杂度—随机种子”描述算法；附录代码须有入口、
依赖版本和输出文件。离散/迭代模型还要写索引约定、初始化、边界更新、稳定性/收敛
条件及失败处理。代码变量与公式变量建立映射表，避免同名异义。

### 4.3 按题型配置验证

- **预测/统计**：按时间或个体隔离回测；报告 MAE/RMSE 等指标、残差/校准和不确定性；
  不把训练集 R² 当泛化证明。
- **优化/决策**：检查每条约束的违反率/余量；报告基线、最优性 gap 或权衡；关键参数做敏感性。
- **机制/仿真**：守恒/边界残差、网格/步长收敛、参数扰动和情景对照至少覆盖两类互补证据。
- **政策/因果**：写识别假设、反事实范围和混杂风险；相关结果不得直接升级为因果结论。
- **证明/解析**：检查定义域、边界值、退化情形和独立推导/反例。

## 5. 图表与附录版式

### 5.1 图表元数据

```yaml
id: fig:q2-error
kind: figure
label: fig:q2-error
caption: <描述对象、范围、指标和结论边界>
cited_by: [claim:q2-stability]
source_artifact: artifacts/q2/error_curve.svg
generator: scripts/plot_q2.py
unit: <坐标轴单位或 none>
legend: <必要时列出>
status: VERIFIED
```

表题放表上、图题放图下只是常见排版规则，最终以官方模板为准。所有图表先在正文被
引用，再出现；caption 不只写“结果图”，而要让脱离正文的读者知道对象、时间/样本
范围、单位和结论边界。数值统一有效位，小数位和缺失值口径写入脚注。

### 5.2 三线表骨架

```tex
\begin{table}[htbp]
  \centering
  \caption{<内容型表题>}
  \label{tab:q2-sensitivity}
  \begin{threeparttable}
    \begin{tabular}{@{}l S[table-format=2.2] S[table-format=2.2]@{}}
      \toprule
      情景 & {指标 1} & {指标 2} \\
      \midrule
      基线 & 1.20 & 0.83 \\
      扰动 & 1.35 & 0.79 \\
      \bottomrule
    \end{tabular}
    \begin{tablenotes}\footnotesize
      \item 注：单位、样本数、区间和缺失值规则写在这里。
    \end{tablenotes}
  \end{threeparttable}
\end{table}
```

示例数字仅是占位，发布前必须替换并回链到 `claim_matrix`。宽表/长表不要挤压正文；
可缩小冗余列、转入附录或提供 CSV，但不能删掉分母和不确定性。

### 5.3 代码附录

优先使用 `listings` 或受控的 `minted`/等效工具：等宽字体、行号、问题/情景标题、
分页不裁切缩进。正文只保留能解释算法的伪代码和关键更新式；附录代码、配置和输出
文件需在 clean-run 中实际生成。代码截图不能作为可复现证据。

### 5.4 论文级文字层级（可配置主题）

把视觉层级写进 `paper_style`，不要靠作者临场手调：

| 层 | 建议的稳定规则 | 验收重点 |
|---|---|---|
| 正文 | 中文正文、数学变量、单位和代码使用可区分且可回退的字体；段落间距/首行缩进统一 | 全文一致，缺字时不改变版心 |
| 标题 | 最多三级；编号、字重和上下间距由模板统一 | 标题不孤行、不与公式/图表相撞 |
| 公式 | 居中或按模板对齐，编号占独立右侧区域；公式前后留出可读间距 | 长公式不溢出，编号不重叠，变量/单位字形稳定 |
| 表格 | 表题、表头、正文、脚注层级清楚；三线规则和列间距统一 | 跨页表头重复，数值小数位/对齐一致 |
| 图 | 图内只保留必要坐标、图例和短标签，主解释放 caption/正文 | 缩到最终版心仍可读，灰度下线型可区分 |
| 附录代码 | 等宽字体、行号和问题/情景标题固定；长行折行策略明确 | 缩进不丢、行号连续、页首/页尾不裁切 |

参考论文展示了“正文中文与数学 Latin 字形分工、公式编号右对齐、表题/图题位置稳定、
代码附录可定位”的效果；这些是排版机制，不是必须复制的字体名称或字号。任何具体字号、
边距、页数、黑白打印要求都要由 `official_format.source_ref` 决定。

## 6. LaTeX/Word 共享中间层

建议将 `problem_contract`、registries、captions 和 claims 存为 JSON/YAML，由两种输出
生成器共同读取：

```text
结构化源 → LaTeX 生成器 → PDF + log + manifest
          ↘ Word/OMML 生成器 → DOCX/PDF + render report
```

Word 版本要建立“标题 1/2/3、正文、公式、图题、表题、代码、脚注”样式；公式用可编辑
OMML/MathType 对象，编号与引用使用可更新域，表格不用空格对齐。导出 PDF 后重新核对
字体替换、域更新、分页和公式断行。LaTeX 与 Word 的数字、label、caption 不得各自改写。

## 7. 渲染 QA 与发布门

### 7.1 编译日志门

至少扫描：

- undefined/unresolved references、重复 label、引用循环；
- missing character、字体回退、Overfull/Underfull box、公式溢出；
- 图表/代码浮动到错误小问、跨页截断、表头未重复；
- 页数、匿名字段、摘要独立性和官方格式版本；
- 参考文献未引用、引用未列出、DOI/网址无法核验。

仓库脚本的 `--release`（或显式组合 `--strict --require-equation-labels --require-float-metadata --forbid-manual-tags`）
会把缺少公式 label、图表元数据、占位符和断裂引用视为阻塞；
手写 `\\tag` 默认只给警告，只有确认当前官方模板不允许手工编号时才加
`--forbid-manual-tags`。这一区分避免把某篇范文的编号习惯误当成普遍规则。

### 7.2 视觉门

在目标尺寸和灰度预览下检查：

1. 公式右侧编号不与正文/边界相撞；
2. 图表、图例、坐标、单位和脚注清晰；
3. 表格没有错误断线或大面积空白；
4. 代码行号、缩进和长行没有裁切；
5. 页眉页脚、页码和匿名信息符合当前官方模板。

### 7.3 状态升级

```text
DRAFT → STRUCTURE_CHECKED → READY_FOR_REVIEW → RELEASED
             ↘ BLOCKED / UNVERIFIED
```

任何关键数字没有 provenance、公式量纲不明、交叉引用断裂、独立验证失败、版权边界
不清或渲染缺陷，都只能停在 `BLOCKED`/`UNVERIFIED`。结构检查通过不等于数学正确。
