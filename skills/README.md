 # 数学建模 Skill Registry v2

 这是仓库的可执行方法论层。唯一入口是 skills/registry.json；每个注册项都有
 SKILL.md、skill-manifest.json、来源标识、输入输出、写入边界和硬门。原始资料
 仍在 Owner 的本地资料目录，仓库只保存蒸馏规则和审计指针。

 `source-provenance.json` 是与注册表配套的机器可读来源台账：只保存外部资料的哈希、
证据类别、支持范围和迁移限制，不保存资料正文。每个 manifest 的 `source_ids` 必须
 能在该台账中解析。

版本迁移与删除记录见 `skills/CHANGELOG.md`。

 ## 体系结构

 固定链适合比赛实时求解：

 charter → scope-lock → question-decomposition → data-and-evidence →
 model-routing → mathematical-derivation → solver-reproducibility →
 validation-and-adversarial-review → paper-and-typesetting → defense-and-release

 DIY 链适合探索和特殊题型：从同一方法卡/工作流块目录选择节点，替换某个小问的
 基线、主模型或备用模型；端口、DAG、证据、复现和发布硬门不能被删除。

 MCM/ICM 在通用链上叠加 mcm-icm-delta；外部 Agent 导出包走
 evidence-reconstruction 旁路；备赛使用 workflow-prep-and-drill。

 ## 技能索引

 | 阶段 | ID | 入口 | 主要产物 |
 |---|---|---|---|
 | 横切 | charter-and-safety | 00-charter-and-safety | run charter、来源台账、权限和状态 |
 | 输入 | scope-lock | 01-scope-lock | problem contract、规则/附件 manifest |
 | 拆解 | question-decomposition | 02-question-decomposition | question map、依赖 DAG、覆盖矩阵 |
 | 证据 | data-and-evidence | 03-data-and-evidence | data contract、变量/单位、无泄漏切分 |
 | 路由 | model-routing | 04-model-routing | baseline/primary/fallback route |
 | 推导 | mathematical-derivation | 05-mathematical-derivation | 方程、假设、离散和解释链 |
 | 计算 | solver-reproducibility | 06-solver-reproducibility | run manifest、结果哈希、复算日志 |
 | 审查 | validation-and-adversarial-review | 07-validation-and-adversarial-review | 验证、敏感性、红队和反例 |
 | 写作 | paper-and-typesetting | 08-paper-and-typesetting | paper contract、LaTeX/PDF、渲染 QA |
 | 学习 | exemplar-mining | 09-exemplar-mining | 范文观察卡、迁移边界 |
 | 发布 | defense-and-release | 10-defense-and-release | 答辩包、release pack、审批 |
 | 增量 | mcm-icm-delta | 11-mcm-icm-delta | Summary、Letter/Memo、美赛检查 |
 | 迁移 | evidence-reconstruction | 12-evidence-reconstruction | 步骤契约、重建报告、PENDING_RELAY |

 工作流入口：

 - workflow-cumcm-main：高教社杯固定主流程；
 - workflow-prep-and-drill：备赛、算法练习、范文精析和限时演练；
 - workflow-diy-puzzle：拼图式自由装配和创新记录。

当前能力目录提供 86 张候选方法卡，覆盖评价/赋权、统计/预测、分类/聚类、灰色与拟合、
机理/PDE/ODE、图论/优化/元启发式、排队/马尔可夫/仿真、验证、论文和答辩。数量只表示
可检索覆盖度；每张卡仍必须经过题面结构、数据/机理证据、baseline 和独立验证四步筛选。

 ## 共同契约

 按需读取共享 references：

 - evidence-and-status.md：claim_class、状态机、冲突和交接包；
 - artifact-contracts.md：problem、question、data、route、run、validation、paper、release 字段；
 - method-routing-matrix.md：结构证据到方法族的路由矩阵和反套用规则；
 - cumcm-review-rubric.md：资料包官方评阅信号的抽象及题型最低证据；
 - paper-layout-profiles.md：国赛/美赛版式 profile、数学表达和 PDF 门；
 - workflow-composition.md：固定链、DIY 端口、DAG 和发布规则。

 资料证据、哈希和限制见 notes/skill-rebuild-material-ledger.md 与
 notes/skill-rebuild-architecture.md。任何“官方要求”都必须重新锁定当届文件；
 模板是 convention，范文是 observation，方法卡是 curated candidate。

 ## 机器校验

 在仓库根目录运行：

     python -X utf8 skills/scripts/validate_registry.py --strict --json
     python -X utf8 skills/scripts/audit_workflow_artifact.py assembly.json --strict --json
     python -X utf8 skills/03-data-and-evidence/scripts/validate_data_contract.py data-contract.json --strict
     python -X utf8 skills/06-solver-reproducibility/scripts/validate_run_manifest.py run-manifest.json --strict
     python -X utf8 skills/tests/run_regression.py

 论文结构脚本位于 08-paper-and-typesetting/scripts，外部运行步骤脚本位于
 12-evidence-reconstruction/scripts。脚本只做结构/证据检查，不替代数学判断、
 独立复算或 Owner 审批。

 ## 安全与维护

 - 只读原始资料；不执行资料包未知宏、安装器、DLL、MEX 或脚本。
 - 原始输入不可覆盖，所有清洗、运行和渲染产物带 revision 与哈希。
 - 不把算法目录文件数量当作适用性，不把模型命中当作答案。
 - 未来信息、未核验规则、乱码、不可复现和越权写入都显式阻断。
 - 新资料或当届规则变化时生成新 source revision，旧产物标 STALE。
 - 用户是最终 Owner；外部提交、推送、删除和发布必须在当前授权范围内进行。

 后端只读接口：

     GET /api/projects/{project_id}/skills/catalog
     GET /api/projects/{project_id}/skills/search?q=...&limit=...
     GET /api/projects/{project_id}/skills/{skill_id}

接口返回 registry_revision、注册项和状态，不执行技能或原始代码。

方法卡通过 `skill_refs` 绑定到本目录的技能；绑定只负责发现和审查路由，不自动替题面
选模。完整回归脚本会验证正例、负例和所有入口，负例“被拒绝”才算通过。
