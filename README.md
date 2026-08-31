# 建模议事厅（G-CUP MAS）

面向高教社杯数学建模竞赛的多 Agent 协作工作台。它把“群聊”作为可视化工作面，把题面—小问—变量/单位—假设—路线—算法—验证—论文 claim 链、版本化工件、证据链、独立质疑和群主审批作为真正的工程控制面。

> 当前目录是一个无需安装依赖即可打开的前端 MVP。默认是明确标注的 `SIMULATED` 演示；以 FastAPI 本地事件源启动后，`?live=1` 会通过 REST + WebSocket 读取真实的本地事件投影。它仍不会自动调用任何付费模型。演示模式中的 revision 使用 `fixture:` 可读 ID；只有连接本地事件源后，才会替换为服务端 `manifest:<64 hex>`。

## 1. 运行前端 MVP

最简单的方式是直接双击 `index.html`。如果浏览器限制本地脚本，可在此目录启动一个静态服务器：

```powershell
python -m http.server 4173
```

然后打开 <http://localhost:4173>。

当前可以体验：

- 三栏群聊界面：群成员、主议事群、任务与证据。
- 用户以群主身份发送指令，模拟 Coordinator 分派和 Agent 回执。
- Agent 卡片、任务 DAG、决策审批、证据预览、事件流和外部 relay 状态。
- `SOLO / LITE / FULL` 模式选择、暂停协作、@提及、搜索和响应式布局。
- 首屏建模链：Q1—Q4 覆盖、路线 A/B 必填字段、题型验证和发布门矩阵；每条消息显示来源、claim class、task/Q、revision、状态和 evidence refs。
- 能力装配工作台：先用“标准工作流”生成带题面契约、参数/场景契约、基线、验证、质疑和写作门的骨架，再切换“自由装配”按端口连接方法卡；每次校验都有 `assembly:<64 hex>`、节点/边差异和缺失硬门提示。
- 动态题面契约：可粘贴任意中文/英文题面，抽取小问、交付动词、变量/约束/数据/验证线索，并把题型推荐明确标成 `HYPOTHESIS`；抽取结果是 `DRAFT_UNVERIFIED`，不替代 Scope-Lock 的逐句核验。
- 资料能力层：资料库不只是文件搜索，还投影出方法卡、工作流块、题型 archetype、预设和一等内容包；内容包可按题面证据、范文结构、方法代码、反例边界、写作模板挂载，并可 resolve 到当前快照的 `kbdoc` 候选。它们仍是可审查候选能力，不是把范文答案直接复制到新题，所有使用都沿用同一来源与 claim 门禁。
- “近十年范文基线”只读说明：基于 2016—2025 的 13 条公开展示/文字镜像记录，明确区分 observed/inferred/hypothesis 和 image-only/奖项未核验缺口。详见 [`docs/exemplar-study-2016-2025.md`](docs/exemplar-study-2016-2025.md) 与 [`docs/modeling-first-workbench.md`](docs/modeling-first-workbench.md)。
- Owner 裁决与未决项：见 [`.collab/decisions/adjudication-2016-2025.md`](.collab/decisions/adjudication-2016-2025.md)。
- 本地资料库：默认只读接入 `C:\Users\zyy20\Desktop\数学建模资料全套包`。点击右侧“资料库”，或在输入框发送 `@知识库 论文模板 写作规范`，即可按年份、模块、类型检索并把 `kbdoc:` 引用挂回群聊；同步中的临时文件不会入库。实现边界和接口见 [`docs/knowledge-base-integration.md`](docs/knowledge-base-integration.md)。
- 小青龙动态身份位：顶栏以 `assets/ip/xiao-qinglong-idle-v3.mp4` 播放一次待机预览，结束或不适合动态播放时自动回退静态脸图；该候选素材尚未作为严格无缝循环母版放行。
- v9 甲骨文·液态玻璃界面：骨纸/墨绿/青铜为主 token，甲骨刻痕只作分区识别，玻璃只用于顶栏与按需控制抽屉；当前 Q、阶段、阻断、路线/验证摘要常驻，消息 provenance 默认折叠但可一键展开。
- v12/v13 质感升级：采用“浮动纸面壳 + 局部液态玻璃”的层级，青甲骨字体仅承担品牌与短标题，群聊正文与证据保持纸面高可读；移动端以固定任务/证据抽屉承载控制面，验收覆盖桌面、平板和 360/390px 手机视口。完整边界见 [`docs/ui-system.md`](docs/ui-system.md) §8–9。
- v13.2 质感增量：左栏加入低对比度小青龙水印，首屏保留可见主视觉；成员通过角色色带与文字状态点快速识别，overview 继续压缩到当前 Q/阶段/路线/验证，QingJia 展示字体采用可回退加载策略。具体验收见 [`docs/ui-system.md`](docs/ui-system.md) §10。
- v13.5 触感收束：聊天背景纹理限制在边缘纸面，右侧普通任务行退为安静的半透明清单，仅当前运行卡保留浮层重量；手机 Toast 在淡入前预留安全带，避免遮挡最后一条消息或输入区。具体验收见 [`docs/ui-system.md`](docs/ui-system.md) §11。
- v10 青甲骨刻体：接入用户提供的 QingJia Oracle Display Regular（WOFF2/TTF），仅用于品牌、首屏标题和短印记；保留 ARPHIC 许可证、修改声明与可重建源数据，并按参考板式加入玉石 seal、淡青描边和圆角工作卡层级。
- v11 QQ/微信式群聊信息流：消息行改为全列布局，Agent 从左侧进入、群主从右侧进入；同一成员两分钟内的连续消息自动收拢头像/元数据，系统通知居中，引用置顶，附件保留安全链接与证据状态，移动端保持无横向溢出。

模型岗位、盲测题集、录用阈值和三种规模配置见 [`docs/model-calibration.md`](docs/model-calibration.md)。

视觉资产 `assets/math-field-bg.png` 是低对比度数学网络纹理，只用于氛围层；界面中的题面、数字、状态和证据均由结构化数据渲染，避免把生成图误当作事实。当前内容仍是 `SIMULATED · fixture`，不能作为真实赛题结论或获奖证明。

## GitHub 协作工程入口

本目录同时承载数学建模协作工程的共享黑板：

- AGENTS.md：Qoder、Codex、Antigravity、Claude API 的职责边界与评审规则。
- TASKS.md：任务状态的唯一事实来源；任务按“待认领 → 进行中 → 待审 → 已完成”流转。
- skills/：审题、建模、求解、验证、写作、终检、范文精析和美赛专项的可执行方法卡；`notes/算法模板盘点.md` 是算法模板库的施工蓝图。
- notes/：共享笔记、材料索引和独立评审记录。
- models/、experiments/、paper/、viz/：模型代码、实验结果、论文与展示产物。
- scripts/agents/review.py：可选的 Claude API 独立评审脚本；密钥只放在本地 .env，不进入提交。

前端工作台与这套协作黑板共用同一项目目录：页面负责实时投影 Q、任务、证据和审批状态，文件与任务记录负责持久化协作事实。.collab/、runtime/ 和本地资料缓存默认不进入公开提交。

本次同步已保留远端 `main` 的资料深挖与 workflow 增量（`origin/main@ffd6001`），并将本地议事厅前端、字体、IP 资产和后端事件源作为同一工程的可运行层；发生冲突时以可运行代码、证据链和追加式历史为合并优先级，不覆盖任一侧的研究记录。

### 连接本地事件源（可选）

在另一个终端运行：

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8787
```

打开 <http://127.0.0.1:8787/?live=1> 即可看到 snapshot、事件序号、CAS 和 WebSocket 回放。若希望开发服务重启后保留控制面状态，可先设置：

```powershell
$env:COLLAB_STATE_FILE = "runtime/collab-state.json"
```

这是单进程原子 JSON journal；Docker Compose 已把宿主端口绑定到 `127.0.0.1`，因为当前服务还没有 OIDC/RBAC，不应直接暴露到局域网。真实模型适配器和密钥不会放进前端。

### 调用本地数学建模资料库

服务启动后可直接调用以下只读接口（不会复制或执行资料）：

```text
GET /api/projects/HGC-MF-2026-001/knowledge/summary
GET /api/projects/HGC-MF-2026-001/knowledge/search?q=遗传算法&top_k=8&with_preview=true
GET /api/projects/HGC-MF-2026-001/knowledge/context?q=论文模板&kind=template&top_k=6
GET /api/projects/HGC-MF-2026-001/capabilities/catalog
GET /api/projects/HGC-MF-2026-001/capabilities/suggest?q=约束优化&limit=8
GET /api/projects/HGC-MF-2026-001/capabilities/content-packs/counterexample/resolve?top_k=6
POST /api/projects/HGC-MF-2026-001/capabilities/problem-contract
POST /api/projects/HGC-MF-2026-001/capabilities/compose
POST /api/projects/HGC-MF-2026-001/capabilities/commit
```

`context` 是给 Agent 适配器的短资料包；每项带 `index_revision`、`snippet/preview` 和严格格式的 `kbdoc:kbdoc_<16位hex>`。内容包 resolve 会额外返回 `coverage`、`evidence_refs` 和抽取状态，便于把“挂载了资料”与“拿到了可定位证据”区分开。它只表示资料线索，不会自动成为论文 claim；引用前仍需 Owner 核对原文件、题面、页码和独立验证。扫描数字与可正文抽取率是运行时快照，资料盘仍在同步时会显示 `LOCAL_PENDING`。

### 能力装配：标准路径与自由组合

右侧“能力装配”有两个互补入口：

1. **标准工作流**：按预测、机制、优化、仿真等 archetype 生成可审计的默认 DAG。它包含四个产品硬门：`problem-decomposition`、`baseline-model`、`validation`、`writing`；参数契约、场景契约和 `critic-challenger` 是推荐扩展。
2. **自由装配**：从能力目录拖入工作流块和方法卡，用有类型端口连接输入/输出。服务端检查引用存在、端口类型、必需输入、DAG 无环、模型到验证到写作的证据链和硬门，不执行模型或代码。

点击“校验装配”得到结构报告；点击“保存草稿”或“提交审查”才会追加 `ASSEMBLY_UPDATED` 事件。差异审计记录上一版与当前版的节点/边变化、内容包挂载变化、创新差异卡和缺失硬门，并保留 `claim_class=derived/hypothesis`；方法卡与工作块不匹配时给出可见提示但不自动改写用户选择。提交审查要求所有硬门通过；它仍不等于数学正确、参数有效或论文可发布。

这种设计把“泛化”落在稳定接口上：任意题面先变成动态小问契约，任意题型再映射到候选 archetype，最后由方法卡与工作流块装配成题目专属 DAG。它不承诺对所有赛题自动得到正确模型；未知机制、缺数据、单位歧义和题面语义必须由 Owner、Scope-Lock、领域专家和独立验证关闭。

## 2. 产品定位

高教社杯不是“让几个模型轮流聊天”，而是一条可审计的建模生产线：

```text
题面与规则锁定 → 数据/机制理解 → 独立路线 A/B/C → 证据化批评
→ 群主路线审批 → 分问实现 → 集成冻结 → 独立验证/反例
→ 论文与答辩 → 清洁环境复现 → 群主发布
```

目标架构中，群聊消息只是上述事件的摘要投影；生产运行时源事实应保存在 `.collab/` 的 charter、task、artifact、evidence、review 和 append-only events 中。当前 MVP 的控制面默认在内存中（可选 `COLLAB_STATE_FILE` 本地 journal），因此不能把演示状态当作正式比赛档案。

## 3. 权限层级

```text
Owner（你，人类群主）
  ├─ 锁定届次/组别/题目/范围
  ├─ 批准路线、模型切换、预算、外部传输和最终发布
  ├─ 暂停、重派、接受风险或终止运行
  └─ 对任何 Agent 的投票/评分拥有最终否决权
        ↓
Coordinator（默认由当前 Codex 根任务担任）
  ├─ 维护 DAG、revision、租约、事件和冲突仲裁
  └─ 不替代独立审查，不越过 Owner 做不可逆动作
        ↓
Worker / Solver / Reviewer / Auditor
  ├─ 只读批准输入，只写专属 write_set
  └─ 不能修改题面、验收条件或另起 Coordinator
```

## 4. 角色与职责

### 常驻核心成员

| 群员 | 职责 | 主要产出 | 默认权限 |
|---|---|---|---|
| Scope-Lock / Sentinel | 逐句锁定题面、附件、单位、约束、交付物和规则版本 | `source_manifest`、`problem_contract`、`coverage_checklist`、`rule_contract` | 读原始输入；只写 `artifacts/scope/` |
| Coordinator / Orchestrator | 唯一总控，拆 DAG、派发、收集回执、冻结 revision、仲裁冲突 | `charter`、`tasks`、`events`、`decisions` | 写控制面；不能伪造证据 |
| Context / Provenance Librarian | 压缩上下文、维护来源、版本、许可证和 claim 索引 | `context_checkpoint`、`claim_index`、`provenance_manifest` | 读已批准工件；写来源目录 |
| Data Engineer / Auditor | 编码、表头、单位、缺失、异常、重复、泄漏、抽样和切分 | `data_dictionary`、`quality_report`、`clean_manifest`、`split_plan` | 不改 raw；写数据派生目录 |
| Model Strategist A | 机制/优化主线，给出 baseline、主路线、扩展和回退 | `route_A_spec`、公式、算法、验证计划 | 只读冻结的子问题契约；写 `routes/A/` |
| Independent Solver B | 用不同模型族/供应商独立提出另一条路线 | `route_B_spec`、独立运行证据 | 看不到路线 A 的排名/自述；写 `routes/B/` |
| Critic / Challenger | 找漏题、量纲错误、不可识别、泄漏、边界反例、过拟合和夸大创新 | `findings`、反例、评分、修复建议 | 只读审查；不能改作者路径 |
| Validation Auditor | 从干净快照复算，做误差、敏感性、稳健性、守恒/收敛检查 | `validation_report`、运行日志 | 只读冻结集成版本；写 `reviews/validation/` |
| Paper / Judge Advocate | 将 VERIFIED 结论映射到评分点、论文结构、图表和答辩 | 论文骨架、摘要、图表、答辩问答 | 只能读已验收 claim；写 `paper/` |
| Release Auditor | 清洁环境重跑、依赖/哈希/匿名/文件结构和提交包检查 | `release_report`、导出包 | 只写审计与发布包；不能自行发布 |

### 按题型动态启用

- OCR / Vision：扫描 PDF、表格、图表、公式；抽取结果必须回到可引用的文本/表格工件。
- Domain Specialist：物理/PDE、生态、经济、交通、医学、社会调查等；只在题面机制确实需要时启用。
- Optimization Engineer：线性/整数/非线性/多目标、可行性、上下界、最优性 gap。
- Simulation Engineer：蒙特卡洛、离散事件、ODE/PDE、网格/时间步收敛。
- ML Specialist：只有样本量、特征结构和独立验证足够时才启用；必须保留透明 baseline。
- Defense Coach：只根据 VERIFIED/ACCEPTED 工件生成陈述与追问回答。
- Resource Manager：监控 token、费用、GPU/CPU、时间盒和重试；超预算先降级模型，不跳过质量门。

## 5. 任务 DAG（FULL 模式）

| 阶段 | 节点 | 依赖 | 可并行性 | 出口门槛 |
|---|---|---|---|---|
| G0 | 建项、权限、预算、快照、规则锁定 | Owner 输入 | 串行 | 原始文件哈希、来源清单 |
| G1 | 题面契约、覆盖表、规则/诚信清单 | G0 | 串行 | 每个小问、单位、硬约束有映射 |
| G2 | OCR/文字/表格/公式抽取 | G1 | 与 G3/G4 并行 | 抽取结果可追溯原文 |
| G3 | 数据质量、泄漏、切分审计 | G1 | 与 G2/G4 并行 | 清洗前后计数、禁止擅自改 raw |
| G4 | 领域机制、因果/守恒、参数来源 | G1 | 与 G2/G3 并行 | 事实/假设/约束分层 |
| G5 | 子问题数学化和接口契约 | G2,G3,G4 | 串行 | 输入、输出、变量、目标、约束齐全 |
| G6 | 路线 A/B/C 独立提出 | G5 | 并行且互盲 | 每条含 baseline、主线、扩展、回退 |
| G7 | Critic、Challenger、评分 | G6 | 审查可并行 | 每个 P1 有定位、证据、反例 |
| G8 | 作者 rebuttal 与修复 | G7 | 按路线串行 | P0/P1 有关闭证据 |
| G9 | Owner 路线审批 | G8 | 串行 | approval_id + 选定/融合接口 |
| G10 | 数据管线和基线实现 | G9 | 可并行 | 脚本自动产出结果 |
| G11 | 分问 Solver/优化/仿真 | G10 | 写集互斥时并行 | 单测、边界、随机种子、失败回退 |
| G12 | 集成和结果冻结 | G11 | 串行 | 跨小问单位/接口/图表一致 |
| G13 | 独立 Validation + Adversarial | G12 | 并行 | clean-run、敏感性、反例、无泄漏 |
| G14 | 论文、图表、答辩 | G9 后可起草 | 内容可并行，数字需等 G12/G13 | 只引用 VERIFIED claim |
| G15 | 复审、修复、回归 | G13,G14 | 按 finding 闭环 | P0/P1 全部关闭或 Owner 记录风险 |
| G16 | Release 审计与 Owner 发布 | G15 | 串行 | 哈希、依赖、匿名、提交包、最终批准 |

并行的必要条件是：输入快照相同、写入范围互斥、验收可独立、不会改变公共接口。任何会改变变量、假设、单位、接口或最终数字的动作必须回到 Coordinator 串行裁决。

## 6. 模型路由：按能力而不是按品牌

“Agent”是逻辑职责，“模型”是执行引擎；一个模型可以承担多个逻辑角色，但会话、上下文、权限和写集必须隔离。后端使用 `ModelGateway`，不把品牌名写死在业务逻辑里。

### 推荐模型槽位

| 槽位 | 适合职责 | 选择原则 | 当前可用候选 |
|---|---|---|---|
| `M0 Router` | 任务分类、去重、心跳、摘要、格式转换 | 低延迟、低成本、结构化输出 | GPT-5.4-mini 或同级小模型 |
| `M1 Coordinator` | 长上下文规划、DAG、冲突仲裁、最终整合 | 最强推理、稳定工具调用、低温度 | Codex 的 GPT-5.6 Sol（或同级旗舰） |
| `M2 Independent Reasoner` | 路线 B、独立推导、反例和审查 | 与 M1 尽量不同供应商/上下文，降低相关错误 | Claude Opus / Antigravity Gemini Pro / 其他旗舰，择一或轮换 |
| `M3 Code & Numerical` | Python、优化、仿真、测试、复跑 | 工具调用和代码可靠性优先，必须进沙箱 | Qoder、Codex、Claude Code 中通过能力评测者 |
| `M4 Vision / OCR` | 扫描题面、表格、公式、图表 | 多模态质量、表格/公式识别、长 PDF 处理 | Antigravity Gemini 多模态或其他视觉旗舰 |
| `M5 Chinese Writer` | 论文、摘要、图表说明、答辩 | 中文技术写作、结构遵循、引用不乱编 | Claude Sonnet/Opus、Codex Terra 或经校准的中文模型 |
| `M6 Domain` | PDE、运筹、生态、经济、医学等 | 按题型临时启用；要求给来源和适用域 | 对应领域强模型或人工专家 |
| `M7 Release / Security` | 复现、敏感信息、提交包审计 | 稳定、保守、只读、可重复 | 与作者模型不同的强模型，或 Qoder + 固定检查脚本 |

### 用你现有工具的起步分配

这是一个起步映射，不是永久绑定；实际运行前应做小型 calibration：

- **Codex**：Coordinator、主路线 A、集成和最终工程仲裁。当前可见的 GPT-5.6 Sol 适合旗舰推理；Terra 适合平衡成本；Luna/mini 适合高频摘要。官方模型指南将 GPT-5.6 Sol 定位为复杂推理与编码的旗舰，并建议按工作负载选择 Terra/Luna。[OpenAI 模型指南](https://developers.openai.com/api/docs/guides/latest-model)
- **Claude**：Independent Solver B、长文档批判、中文论文二审；关键是用独立上下文，不把 A 的结论提前告诉它。
- **Qoder**：代码/数据工程、脚本化清洗、测试和可复现运行；让它拥有终端/代码工具，但不拥有题面范围或最终发布权限。
- **Antigravity**：视觉/OCR、第二家独立审查、外部 Challenger；若尚未建立 connector，只生成 `PENDING_RELAY`，不把它显示为在线完成。
- **其他模型**：只按能力评测接入，例如数学推导、PDE、优化、中文写作、视觉识别；不能因为“更大”就替代验证。每个候选至少记录 `provider/model/version/context/tool_caps/cost/latency/data_policy`。

### 最小与完整配置

- **预算有限（3 个模型实例）**：`Coordinator（强推理） + Solver（可执行代码） + Critic（不同模型/不同上下文）`。其他角色串行模拟。
- **标准竞赛配置（7 个实例）**：Coordinator、Scope/Vision、Data、Solver A、Solver B、Critic/Validation、Writer/Release。
- **FULL 竞赛配置（10–14 个逻辑 Agent，按阶段弹性启动）**：常驻控制面 3 个，读题期 3–4 个，路线期 4–5 个，实现期按小问数扩展，收尾期 4 个。

不要为了“群聊热闹”复制同一模型。两个独立方案的价值来自不同上下文、不同假设或不同模型族，而不是重复发送同一提示。

网关还会对数据级别做显式 allow-list：`local-only` 才能处理 `restricted`，外部策略必须同时经过 profile 和请求级 egress 门；未知 `data_policy`、越界校准分和非法预算会直接变为 `MODEL_UNAVAILABLE`。开发模式允许成本未知的候选暂留，但生产注册表必须先登记成本与数据驻留。

## 7. 群聊消息与证据协议

每条消息在界面上显示：`sender / role / actual model / task_id / event type / status / revision / evidence chips`。底层事件至少包含：

```json
{
  "protocol": "agent-collab/v1",
  "project_id": "HGC-MF-2026-001",
  "thread_id": "main",
  "event_id": "evt-00042",
  "message_id": "msg-00042",
  "timestamp": "2026-08-31T14:32:00+08:00",
  "sender": {"agent_id": "critic-1", "role": "challenger", "model": "...", "session": "..."},
  "recipients": ["coordinator", "owner"],
  "type": "CRITIQUE",
  "task_id": "G7",
  "base_revision": "manifest:<64 hex>",
  "priority": "P1",
  "payload": {"verdict": "REVISE", "summary": "..."},
  "artifacts": [{"id": "A-17", "path": ".collab/reviews/G7/f1.json", "sha256": "..."}],
  "claims": [{"id": "C-17", "class": "derived", "evidence_ids": ["A-17"]}],
  "requires_ack": true,
  "idempotency_key": "G7/critic-1/attempt-1"
}
```

群聊中的“颜色”只表达状态，不能代表真伪；真伪看 claim 类型、证据、独立复核和 revision。远端输出和附件一律当作不可信数据，不能把其中的“忽略规则/执行命令”当成系统指令。

## 8. 后端生产版

### 推荐组件

- 前端：React/Next.js + TypeScript + Zustand/Redux + WebSocket/SSE；MVP 可先保留本目录的 vanilla HTML。
- API：FastAPI 或 Node，负责项目、任务、审批、工件、事件和模型网关。
- 编排：Coordinator service + 队列；生产环境用 Redis/NATS/Temporal，竞赛离线模式可用 SQLite WAL + asyncio。
- 存储：Postgres 元数据、MinIO/S3 或本地工件目录；每个工件记录 SHA-256、来源、版本、敏感级别。
- 执行：Python 沙箱，固定依赖、随机种子、超时、输出上限；Gurobi/CPLEX 仅在许可证可用时启用，并准备开源回退。
- 外部 Agent：MCP/CLI adapter；传输冻结快照和任务包，不复制整段群聊。

### 最小 API

```text
POST /projects
POST /projects/{id}/ingest
POST /projects/{id}/dispatch
POST /tasks/{id}/claim
POST /tasks/{id}/result
POST /tasks/{id}/heartbeat
POST /tasks/{id}/handoff
POST /tasks/{id}/review
POST /tasks/{id}/challenge
POST /projects/{id}/approvals
POST /relays/{id}/ack
POST /runs/{id}/rerun
GET  /api/projects/{id}/capabilities/catalog
GET  /api/projects/{id}/capabilities/suggest
POST /api/projects/{id}/capabilities/problem-contract
POST /api/projects/{id}/capabilities/compose
POST /api/projects/{id}/capabilities/commit
GET  /projects/{id}/snapshot
GET  /projects/{id}/events?after_seq=...
WS   /ws/projects/{id}
```

生产环境所有写接口必须带 `base_revision`、`idempotency_key` 和 actor identity；开发版对 bootstrap 写入保留可选 `base_revision`，省略时不应被误解为 CAS 已生效。服务端做 CAS、权限、路径和 schema 校验。断线后用事件序号补发，不能靠前端猜测状态。

## 9. 竞赛专属质量门

建议默认阈值（可由 Owner 在 charter 中调整，但不能绕过）：

- 题面/规则覆盖率：100%。
- 关键 claim → evidence 覆盖率：100%。
- 关键模型：至少 baseline + 主路线；若没有第二路线，必须记录理由。
- 量纲、符号、边界/初始条件和可识别性：全部通过。
- 预测题：独立回测/CV/留出与不确定性；仿真题：守恒、边界、收敛；优化题：可行性、约束违反率、敏感性。
- 独立验证：至少一名 reviewer 不读作者自述，仅读冻结工件和运行入口。
- P0/P1：全部关闭，或由 Owner 显式记录 accepted-risk；否则禁止 `ACCEPTED`/`RELEASED`。
- 清洁环境复现：关键命令成功率 100%，结果表由脚本生成，依赖/种子/日志齐全。
- 规则与诚信：当届官方通知、赛题、AI/外部资料、查重、匿名和提交格式逐项留来源；不把往届规则泛化到本届。

路线评分可以使用：

```text
route_score = Σ(weight_i × score_i) − penalty
```

参考维度：problem_fit、mathematical_correctness、data_validation、implementability、optimization、originality、interpretability、robustness、paper_score。评分是决策支持，不能代替 Owner，也不能代替数学证明或运行证据。

## 10. 安全与跨平台边界

- 默认能力拒绝：Agent 只读声明输入，只写自己的目录，无 secrets、网络、删除、发布权限。
- 路径必须限制在项目根目录，拒绝绝对路径、`..`、链接和控制文件越权。
- lease、fencing epoch、CAS 和原子事件追加防止过期 Agent 覆盖新结果。
- relay 需要 sender/recipient identity、nonce、expiry、idempotency、input hash 和 approval_ref；哈希本身不是身份认证。
- 没有共享目录时传递固定 Git commit 或 manifest + 沙箱归档；未完成 ACK/哈希核验时状态为 `PENDING_RELAY`。
- `publish / delete / send / cancel` 等外部动作必须经过 Owner 明确批准。

## 11. 建议实施顺序

1. **MVP（当前已可跑）**：本地事件源、能力目录、动态题面契约、标准/自由 DAG 装配、差异审计、`ASSEMBLY_UPDATED` 回放、4 个逻辑 Agent（Coordinator/Scope/Model/Critic）、幂等/CAS/租约/审批/relay 边界。
2. **竞赛版**：接入 Data/Validation/Paper/Release，加入 Git worktree 或 manifest、独立模型上下文、完整门禁和离线导出包。
3. **跨平台版**：为 Antigravity、Claude、Qoder 实现统一 adapter，先做 connectivity smoke test，再开放敏感数据传输。
4. **生产版**：Postgres + Redis/NATS/Temporal + 对象存储 + OIDC/RBAC + 审计链 + 模型评测路由。

下一步如果要把这个 MVP 接成真实系统，优先替换单进程 journal 为 SQLite WAL/Postgres，接入真实 `ModelAdapter`，再启用 OIDC/RBAC 和签名 relay；前端布局和交互可以直接沿用本目录。

## 12. Workspace / repo catalog（T07）

除了外部数学建模资料盘，Agent 还可以按需挂载本仓库中已审核的协作上下文。只读接口不扫描用户资料根、不读取 secrets、不执行仓库文件，仅允许 `README.md`、`TASKS.md`、`AGENTS.md`、`app.js`、`index.html`、`styles.css`、`docker-compose.yml` 及 `backend/`、`assets/`、`docs/`、`skills/`、`notes/`、`workflows/`、`models/`、`paper/`、`viz/`、`scripts/`、`experiments/`。

```text
GET /api/projects/HGC-MF-2026-001/workspace/catalog
GET /api/projects/HGC-MF-2026-001/workspace/search?q=source%20refs&top_k=20&path=docs
```

响应携带 `manifest_sha`/`manifest_sha256`、`items`、`counts` 与 `repo:<relative-path>` `source_refs`。正文检索仅对不超过 1 MiB 的文本文件提供有界片段；路径穿越、绝对路径、隐藏目录、符号链接和超大文件均 fail-closed。`repo:` 可以作为有界候选指针随消息记录在 `evidence_refs` 字段中，但只代表“该仓库快照中存在候选上下文”，不代表内容已适用于当前题目，更不足以单独构成论文证据；必须继续经过题面契约、数据/数学验证、独立审查和 Owner 门禁。若 manifest 变化，Agent 应丢弃旧上下文并重新读取 catalog。

## 13. v14 质感原则

v14 的视觉目标是“可进入、可停留、可判断”，而不是增加更多装饰：

- 用一张连续的暖纸面承载群聊，把玻璃限制在顶栏、悬浮工具条和按需控制抽屉；消息、证据和公式保持接近不透明，优先可读性。
- 只保留一个主浮层（当前运行/当前 Q），普通任务行改为安静清单；边缘高光、短软阴影和按压下沉表达触感，不用持续动画制造高级感。
- 小青龙与甲骨印记是品牌记忆点，不承担状态语义；状态必须同时写出文字、claim class、evidence 和 revision。
- 首屏信息优先级固定为：当前 Q → 阶段与阻断 → 消息正文 → 证据/provenance → 任务控制；低频字段按需展开。
- v14 的“高端”结论必须以多视口截图、无横向溢出、字体回退、Toast/composer 不相交和 reduced-motion 回归为依据；当前本地服务仍是 offline-dev，不应包装成生产级协作或模型调用。
- 当前界面版本为 `v14.2.13`：1321–1360px 临界宽度保留完整气泡，≤760px 桌面窗口收束 hero/Q 轨以保留两条近期消息，手机 Q 轨改为单行编号/状态；成功连接反馈由顶栏承载，避免 toast 遮挡工作区。
