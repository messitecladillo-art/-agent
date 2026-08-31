# 模型校准与动态分工

这份文档解决“模型越多越好”的误区。系统不按品牌投票，而是先给每个候选模型做同一套小型盲测，再把能力分配给逻辑岗位。版本、套餐、上下文上限和价格会变化，运行时必须记录实际 `provider/model/version/effort`，下面的品牌只作候选。

## 1. 角色槽位与默认候选

| 槽位 | 主要工作 | 首选候选 | 备选/降级 | 不授予的权限 |
|---|---|---|---|---|
| M0 Router | 分类、去重、摘要、格式转换 | Codex 小型/低成本模型 | Qoder 快速档、其他小模型 | 改题面、改结果、外发 |
| M1 Coordinator | DAG、上下文包、冲突仲裁、预算 | Codex GPT-5.6 Sol | GPT-5.6 Terra、同级旗舰 | 独立 Critic 身份、自动发布 |
| M2 Route-A | 机制/优化主线、公式和算法 | Codex GPT-5.6 Terra/Sol | 其他高推理模型 | 读取 Route-B、改公共接口 |
| M3 Route-B | 独立统计/仿真路线 | Claude Opus 独立会话 | Antigravity Gemini Pro、其他不同供应商旗舰 | 读取 Route-A 的解释/评分 |
| M4 Code/Data | 清洗、Python、优化器、测试、复跑 | Qoder 工具/代码档 | Codex、Claude Code | raw 覆盖、秘密、发布 |
| M5 Vision/OCR | 扫描题面、公式、表格和图 | Antigravity Gemini 多模态 | 其他视觉旗舰/OCR 专用模型 | 直接把 OCR 猜测写成事实 |
| M6 Critic/Red Team | 反例、量纲、泄漏、外推、提示注入 | Claude/Antigravity 中与作者不同的会话 | Codex 独立会话、专门测试模型 | 修改作者工件、关闭自己的 finding |
| M7 Validation/Release | clean-run、统计验证、提交审计 | Codex GPT-5.5 + 固定脚本 | Qoder、另一供应商审查模型 | 自行接受 P0/P1、外部提交 |
| M8 Writer/Defense | 中文论文、图注、答辩 | Claude Sonnet/Opus 或 Codex Terra | 经过中文写作盲测的模型 | 读取未验收数字 |

### 你现有工具的建议起步映射

- **Codex**：根 Coordinator、路线 A、集成、最终工程仲裁；同一产品内也要使用独立会话和不同上下文，不能把“同品牌”当作独立证据。
- **Claude**：路线 B、长文档二审、Critic；每次路线任务从冻结快照新开上下文。
- **Qoder**：数据/代码/测试执行；它是工具型工位，不让它决定题面范围或最终路线。
- **Antigravity**：视觉/OCR + 第二供应商 Challenger；当前没有验证过的 connector 时只产生 relay 包，状态保持 `PENDING_RELAY`。
- **其他模型**：只有在校准集上证明某项能力更强，才占用一个槽位。可以临时接入 PDE、运筹优化、中文写作、OCR、检索或安全专长模型，但必须拥有独立写集和验收人。

## 2. 盲测题集

每个候选模型至少跑 12 个小题，题目与金标准/评分标签隔离：

1. 逐句题面抽取（含单位、边界和交付物）；
2. 扫描表格/公式 OCR；
3. 数据缺失、重复和目标泄漏审计；
4. 量纲与符号检查；
5. 机制/因果假设识别；
6. baseline + 主路线 + 回退路线；
7. 约束优化可行性与上下界；
8. 仿真守恒/边界/收敛测试；
9. 独立反例与最小复现命令；
10. Python/LaTeX clean-run；
11. 中文摘要、三线表和答辩追问；
12. 提示注入、敏感信息和引用幻觉识别。

每题保存 `input_manifest`、提示版本、模型版本、工具权限、输出 hash、token/费用、延迟、人工盲评和失败原因。禁止把同一个模型之前的答案放入下一题上下文。

## 3. 评分与录用规则

```text
capability_score = 0.30 correctness
                 + 0.20 completeness
                 + 0.20 reproducibility
                 + 0.15 evidence/provenance
                 + 0.10 robustness
                 + 0.05 latency/cost
```

- Coordinator：推理/规划/工具调用各 ≥ 8/10；冲突仲裁不允许把多数票当证明。
- Route-A/B：数学正确、题面覆盖、验证设计各 ≥ 8/10；不能复现的数字直接失败。
- Code/Data：关键脚本 clean-run 成功率 100%，不能用手改结果补分。
- Critic：隐藏缺陷命中率 ≥ 70%，且每条 finding 可定位、可复现；只写审查目录。
- Validation/Release：独立复跑成功率 100%，P0/P1 漏报为淘汰项。
- Writer：事实/数字引用覆盖率 100%，不生成不存在的文献或把 `PRODUCED` 写成 `VERIFIED`。

同分时优先选择数据驻留更安全、工具权限更窄、成本/延迟更低者；高风险任务宁可 `MODEL_UNAVAILABLE`，也不静默降级到能力不匹配的模型。

## 4. 动态路由规则

1. 先锁定数据分类和 input revision，再做 capability match；敏感数据默认只给本地/获批模型。
2. 先选满足全部硬能力的候选，再按校准分、当前预算、延迟和故障率排序；未知数据分级、风险等级、预算或工具要求一律 fail-closed。
3. 失败只在同一能力集合内 fallback；切换模型会记录新 `run_id`，不会覆盖旧结果。
4. 路线 A/B 必须跨上下文，最好跨供应商；Critic/Validation 不能读取作者自述。
5. 外部模型只接收最小冻结包，不发送整段群聊；没有 authenticated ACK + input hash 时维持 `PENDING_RELAY`。
6. 每次比赛前重新跑 smoke test；模型版本、套餐或工具能力变化即使名字不变也要重新校准。

数据策略本身也采用显式 allow-list：`public-only` 只能读 public，`internal-only`
可读 public/internal/confidential，`local-only` 才可读 restricted，
`external-approved`/`external-only` 只能读较低敏感级别且必须同时打开请求级 egress。
未知 `data_policy`、负预算/延迟或越界校准分会被 Gateway 拒绝；成本未知的候选在开发模式可保留但必须在生产注册表预授权。

Gateway 的开发实现会把 `version`、`reasoning_effort`、`tool_permissions`、`calibration_score`、成本/延迟估计写入 run metadata；适配器抛异常或返回未知状态时只在同一能力集合内 fallback。`R5`（外发、发布、删除、接受高风险等）还必须同时提供 Owner `approval_ref`，模型本身不能越权批准。

## 5. 推荐的三种运行规模

| 规模 | 实际模型实例 | 逻辑岗位 | 适用 |
|---|---:|---:|---|
| Starter | 3 | 7 | 预算紧；Coordinator + Code/Data + Independent Critic，其他岗位串行 |
| Standard | 6–7 | 12–14 | 推荐日常参赛；A/B、Critic、Validation、Writer、Release 都有独立会话 |
| Championship | 8–10 | 15–18 | 题型复杂/高风险；按小问弹性启用领域、优化、仿真、OCR和答辩岗位 |

逻辑岗位数量不是并发数量。系统默认 `max_depth=1`、`max_parallel=4`，由 Owner/Coordinator 根据时间盒和预算调整；不能为了“群聊热闹”复制同一模型。
