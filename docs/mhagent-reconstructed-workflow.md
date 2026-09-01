# MHAgent 赛题 A：运行证据反推与迁移说明

状态：`READY_FOR_REVIEW`。本文和同目录 Skill 只固化“可观察证据、可复用接口和未决问题”，不宣称结果包中的数学结论已经被本仓库独立复算。

## 1. 来源与读取边界

来源文件：`MHAgent_赛题A_全部_20260828_103359.zip`（本机原始位置记为 `<LOCAL_SOURCE>`，不写入仓库）。

本次只读了压缩包目录、`README.txt`、`manifest.json` 和其中的阶段日志/产物清单，没有把题面、论文、数据或生成代码复制进仓库，也没有执行压缩包内脚本。README 给出的复现入口是：

```text
cd workspace
pip install -r code/requirements.txt
python code/main.py
```

manifest 显示 7 个步骤、2000 条日志上限、`_sub_steps_pruned=true`，且 `output_files` 为累积列表。两个前置步骤没有对应的 Claude 日志，因此下文对它们的具体操作只作 `INFERRED`，不把日志缺失解释为步骤未执行。

## 2. 七步能力契约

`skills/mhagent-evidence-reconstruction/references/step-contracts.json` 是机器可读真相源。每一步都把输入、输出、职责、方法链、验证门、checkpoint 声明、交接、证据引用、失败策略和开放问题写成字段；运行：

```text
python skills/mhagent-evidence-reconstruction/scripts/validate_step_contract.py
```

七步的可迁移解释如下：

| 步骤 | 观察到的能力 | 可装配的拼图接口 |
|---|---|---|
| 题赛分析 | 题面抽取、事实/规则、单位、能力和数据画像 | `problem-decomposition` + `parameter-contract` |
| 建模设计 | 子问题模型链、假设、共享参数账本、不变量 | `baseline-model` / `mechanism-model` / `scenario-contract` |
| 编程实现 | 参数检查、求解器、退化处理、结果 provenance 和审计 | `data-audit` + `simulation` + `validation` |
| 数据图表 | 图表 recipe、表格、TikZ、标签/单位登记 | `writing` 的 figure/table 子块 |
| 流程架构图 | 模型依赖与交接的 HTML/PDF 可视化 | `workflow/roadmap` 子块（须在能力目录中显式登记，只表达已批准事实） |
| 论文撰写 | 推导—算法—结果—验证链和引用/附录装配 | `writing` + 数学表达 Skill |
| 编译终检 | 编译、引用、页数、匿名、资源和发布门 | `critic-challenger` + `release-compliance` |

上表的 block 名称优先复用仓库现有能力目录；它们是迁移映射，不是对 MHAgent 内部工具名的猜测。

## 3. 观察到的模型链（仅作为能力样例）

结果包报告的样例链是：Q1 使用深度平均二维浅水方程、Arakawa C-grid、科氏力、非线性二次底摩擦、潮汐边界和表层 Ekman 诊断；Q2 使用两层约化重力、正压/斜压分解、三情景和临界根。它们说明“题面事实 → 参数账本 → 机制模型 → 数值验证”的接口形态，但不能泛化为所有赛题的默认模型。

迁移到新题时，必须重新做：题面锁定、参数来源、适用条件、离散/求解选择、独立复算和灵敏度分析。若题目没有物理机制，不应因为本结果包出现 PDE 就强行套用。

## 4. 必须保留的限制与冲突

- `model_ids` 是不透明 ID，不反解为具体模型或厂商。
- checkpoint 在步骤元数据中有声明，但 `workflow.enable_checkpoints=0`，且没有暂停事件证据；运行时审批状态记 `unknown`。
- `AUDIT_REPORT.md` 仍记录 `fatal=2, warn=1`：1200/8000/44712 是 SI 换算未直出，9.49 是临界值上界舍入；论文报告将其解释为误报，但未见独立裁决证据。契约将其保留在 `comp-code.open_questions`，并要求 fail closed。
- `PAPER_DATA_CHECK_REPORT.md` 仍写着“待 Claude 自检”，不能当作已完成的独立论文数据审计。
- 论文阶段报告与最终编译报告出现 63/64 页快照漂移，应重新对带哈希的最新 PDF 做裁决。
- `DATA_PROFILE.json` 显示外部文件数为 0；这只说明该样例是机制建模输入，不说明一般赛题不需要数据审计。

## 5. 固定方案 + DIY 使用方式

固定方案：按七步顺序运行，每步通过对应验证门后才能交接。编程审计或论文数据审计有未决 fatal 时，后续图表、论文和发布步骤只生成带阻断标记的草稿。

DIY 方案：从七个步骤中选择拼图块，再在“建模设计”和“编程实现”中替换已有方法卡；每一块必须声明 `input_schema`、`output_schema`、适用/禁用条件、来源和验证器。允许并行的仅是互不写同一边界的图表、代码复核或文献整理；最终仍回到唯一的协调者和终检门。

## 6. 交接与外部 Agent

交接以版本化文件、manifest SHA-256 和 append-only 事件为准，聊天只作通知。每个 handoff 应包含发送方、接收方、协议版本、nonce、基线 revision、证据等级、命令/退出码、未决项和下一动作。未连接的 Antigravity 等外部 Agent 只能收到 `PENDING_RELAY`，不可声称已经同步。

## 7. 下一步

1. 由独立 Critic/Auditor 只读复核七步契约与证据引用。
2. 对 fatal=2、待 Claude 自检和 63/64 页漂移建立裁决记录；关闭前保持 `READY_FOR_REVIEW`。
3. 用一份不同题型的真实题面做前向夹具，检查契约能否泛化；通过后再把映射接到生产知识库或真实模型 adapter。
