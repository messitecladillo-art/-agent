# 实验日志

> 每次实验一条记录，**只追加不修改历史**。格式见下方模板。

---

<!-- 模板：
### 2026-08-31 · T-xx · 简短描述
- 目的：
- 配置/数据：（参数、数据版本、随机种子）
- 结果：（指标、耗时、输出文件路径）
- 结论/下一步：
-->

### 2026-09-01 · T-14 · 融合议事厅前端与青甲骨刻体
- 目的：将本地建模议事厅前端、远端协作知识库和用户提供的 QingJia Oracle Display 资源合并到同一工程。
- 配置/数据：远端 main 4e9b361e416fd75dd3840fbb01b8338a00bdec17；字体源包 SHA-256 117A6D312B1D75967B5A0CB5A83322224FBD896752F48CBAD0484820CFE41E1A；页面版本 oracle-glass-qingjia。
- 结果：生成 WOFF2/TTF，保留 ARPHIC 许可证、修改声明和可重建源；合并 skills、notes、models、paper、viz、scripts、TASKS.md、AGENTS.md；前端与后端检查通过。
- 结论/下一步：待完成远端分支保护/推送前的密钥扫描与全量测试后，由 Owner 批准发布到 main。

### 2026-09-01 · T-15 · QQ/微信式群聊信息流
- 目的：修正消息区域的空间关系，使其符合群聊阅读习惯并适配手机端。
- 配置/数据：前端版本 oracle-glass-qingjia-chat-v11；连续消息窗口 2 分钟；附件最多 4 个；安全链接仅允许当前页面/API 同源 HTTP(S)。
- 结果：Agent 左对齐、群主右对齐、系统事件与日期居中；连续消息收拢头像/元数据；引用置顶；桌面与 390/360px 视口无横向溢出；95 个后端测试通过。
- 结论/下一步：提交前进行密钥/大文件扫描、合并远端 main，并在推送后复核公开仓库构建结果。

### 2026-09-01 · v12/v13 · 浮动纸面壳与甲骨文字体边界
- 目的：把甲骨文、青甲骨字体和液态玻璃收束为可长期使用的界面语言，改善高端感而不牺牲数学建模信息密度。
- 配置/数据：基线 `working-tree:v12-brand`；范围仅为 UI 规范、README、任务看板和实验记录；字体资产为 `assets/fonts/qingjia/QingJiaOracleDisplay-Regular.woff2`。
- 结果：记录浮动纸面壳、局部玻璃、字体使用边界、群聊四层信息优先级、移动抽屉约束与五组浏览器回归指标。要求正文/证据使用高不透明纸面，甲骨字符只作辅记，移动聊天区保持单列。
- 结论/下一步：代码验收沿用 v11/v9 的浏览器回归与后端测试；推送前仍需执行密钥扫描、大文件扫描和远端融合后的全量测试。

### 2026-09-01 · v13.2 · 小青龙锚点与首屏质感增量
- 目的：在极简纸面壳上补足品牌记忆与角色可识别性，同时保持数学建模首屏的信息优先级。
- 配置/数据：基线 `working-tree:v13.2`；小青龙左栏水印低对比度显示；主视觉保留在首屏；角色使用色带与文字状态点；overview 仅保留 Q/阶段/路线/验证摘要；展示字体采用可回退加载策略。
- 结果：文档明确了水印不遮挡交互、主视觉不承载事实、状态不依赖颜色、字体失败不破坏布局等边界；回归口径为后端 95 tests 与 1440×900、1024×768、768×1024、390×844、360×800 多视口检查。
- 结论/下一步：推送前应以实际浏览器结果核对水印层级、主视觉可见性、字体网络失败回退和移动抽屉；继续执行密钥扫描、大文件扫描与远端融合后的全量测试。

### 2026-09-01 · v13.5 · 触感层级与 Toast 安全带
- 目的：解决“没有质感/没有兴趣使用”的剩余视觉问题，同时保持极简和群聊优先的信息架构。
- 配置/数据：`oracle-glass-qingjia-tactile-v13.5`；聊天纹理桌面 `.29`、窄屏 `.20` 并使用径向遮罩；右栏普通任务/决策/证据行取消常驻阴影；Toast 采用 `prepare → show` 两阶段和 56px feed 安全带。
- 结果：1440×900、1024×768、768×1024、390×844、360×800 均无横向溢出；QingJia 字体检查通过；实际 Toast 淡入/淡出时最后气泡与 composer 保持可见间距；后端 95 tests 通过。
- 结论/下一步：视觉层级可发布；推送前继续执行远端融合、密钥/大文件扫描，并在桌面 App 中复核一次真实 Toast 状态。

### 2026-09-01 · v13.5.3 · 移动控制面板清晰度修复
- 目的：解决窄屏打开控制面板后，半透明遮罩与抽屉处于不同堆叠上下文导致文字整体发糊的问题。
- 配置/数据：将 `#panelBackdrop` 放入 `.app-shell` 的同一层级；遮罩 z-index 10、抽屉 z-index 20；抽屉移动端改为不对自身内容施加 `backdrop-filter` 的不透明纸面玻璃。
- 结果：390×844 与 360×800 抽屉正文清晰，背景仍保持柔和压暗；抽屉、遮罩和 Toast 无交互遮挡；页面保持单列且无横向溢出。
- 结论/下一步：移动端抽屉层级满足发布门槛；继续执行远端合并后的全量回归与公开仓库推送核验。

### 2026-09-01 · T-16 · 远端资料与前端工程安全合并
- 目的：在不覆盖议事厅可运行层的前提下，吸收远端 `main` 的资料深挖、Skill 08、美赛 workflow 与算法模板蓝图。
- 配置/数据：本地基线 `36621bb`；远端基线 `ffd600101ce1004e8c355034f4a153ad23867dc4`；普通 merge（`--allow-unrelated-histories`），无强制覆盖。
- 结果：保留前端、后端、字体/IP 资产与本地 UI 记录；吸收远端新增知识/技能文件与 `.env.example`；冲突文档按“可运行代码 + 追加历史 + 远端评阅增量”人工处理。
- 结论/下一步：合并后重新执行 95 个后端测试、浏览器五尺寸回归、密钥模式扫描和大文件扫描，再推送 `main`。

### 2026-09-01 · v14.2.13 · 质感与阅读空间最终回归
- 目的：把“没有质感”拆成可观察的材质层级、边界完整度和低高度可停留性，并完成 workspace catalog 挂载验收。
- 配置/数据：前端 `oracle-glass-qingjia-tactile-v14.2.13`；运行时 allowlist manifest 以最终 `/health` 与 catalog 响应为准（本日志为 append-only，追加记录会产生新的 runtime revision）；视口 1440/1366/1350/1340/1321×900、1280/1180/1024×768、1440/1366/1280/1024×720、390×844、360×800。
- 结果：宽屏标题/状态/搜索命中区无重叠；低高度桌面收束 hero/Q 后至少保留两条完整近期消息；手机 Q 轨改为单行编号/状态，抽屉面板 z20 高于遮罩 z10；所有页面无横向溢出，成功连接提示静默留在顶栏；workspace catalog 86 项/67 项可检索/13 项资产，`skills` 检索返回24项，越权路径 HTTP 400；后端 `100 passed`，compileall、Node syntax、CSS 花括号、密钥/大文件扫描通过。
- 结论/下一步：视觉与本地运行门槛通过；`source_integrity=STALE_DECLARATION` 仅表示被忽略的旧 `.collab` 声明未更新，不把它当作内容正确性或题面适配证明；生产版仍需真实模型 adapter、RBAC、签名 relay、持久化队列和语义索引。

### 2026-09-01 · T-17 · 一等奖范文数学表达与排版 Skill
- 目的：从用户提供的校赛一等奖论文中提炼可迁移的数学语言、推导链、公式/图表交叉引用和复现排版门，形成可装配的团队 Skill。
- 配置/数据：参考 PDF `C:\Users\zyy20\Downloads\数学建模校赛第五版.pdf`，41 页 A4，SHA-256 `6e330b3520ce57b4fa9de3674e3dead4eef7bcf0fcc20ad08af1264f3ba48eae`；只提交抽象规则、结构化契约、审计脚本和正反例夹具。
- 结果：新增 `skills/math-modeling-mathematical-writing/`（L0–L6 工作流、推导/版式指南、三类注册表、LaTeX/契约审计、前向回归）；Skill 校验、脚本编译、夹具、后端 `134 passed`、Node 语法和 backend compileall 均通过；workspace catalog 检索到入口文件；MiKTeX XeLaTeX 对 good fixture 双遍编译成功，`pdfinfo`/PNG 视觉抽查通过（仅为夹具，不代表正式论文渲染门）。
- 结论/下一步：本 Skill 以 `READY_FOR_REVIEW` 结构状态交付；它不替代独立数学正确性、官方格式锁定、数据审计和人工渲染 QA。

### 2026-09-01 · T-18 · 固定方案与 DIY 工作流拼图
- 目的：把数学建模求解过程做成“固定可选工作流 + 自主拼图装配”，并将小青龙视觉资产用于步骤识别，而不让生成图承载数学事实。
- 配置/数据：前端 `workflow-puzzle.js` v1.17；后端能力目录 `capability-catalog/v1`；ImageGen 资产 `assets/workflow/qinglong-puzzle-guide-v1.png`、`qinglong-puzzle-atlas-v1.png`；方法卡 54 张、工作流块 13 个、固定方案 3 条。
- 结果：静态演示回归通过（固定方案预览/应用、DIY 插入/移动/替换/移除、方法抽屉、硬门提示）；实时目录回归显示 `catalog=live`、服务端 revision、problem/data/writing/defense 等步骤各有多张类型匹配卡；实时目录首次读取期间 fixture 可编辑，升级后保留草稿和选中块；浏览器错误/警告为 0。`python -m pytest backend -q --basetemp .pytest-tmp-final`：138 passed；默认临时目录另有 1 个既有 WinError 5 环境错误，已用仓库内 basetemp 重跑排除。
- 结论/下一步：拼图层达到结构可审交付；“结构可审”不等于数学结论已验证。继续保留 Owner 审批、题面锁定、参数来源、独立复算和最终论文排版门。

### 2026-09-01 · T-18.1 · 拼图层竞态与缓存版本收口
- 目的：关闭“检查返回旧快照覆盖新插入块”和静态资源缓存旧版本的发布风险。
- 配置/数据：前端版本 `v14.2.16` / `workflow-puzzle.js v1.20`；固定路线应用携带预览的完整 `block_ids`；编辑后清空旧 validation，显式检查前发送按钮保持禁用；LIVE bridge 空/失败响应不再回退为本地成功；live URL 缺少宿主桥时直接阻断写操作；异常/重复固定块清单拒绝静默应用；目录 revision 变化会清空旧绿灯，草稿恢复拒绝被 canonical 适配器静默截短的结果。
- 结果：实时浏览器回归显示固定方案预览 13 块、应用后 13 块；检查中立即插入后 15 块在 0/0.9/3.1 秒均保持，门禁持续“等待检查当前链路”；再次检查后结构可审、发送按钮启用；浏览器日志 0；HTTP 根页、拼图脚本、两张 ImageGen PNG 均 200，越权 PNG 404；后端 `138 passed`。
- 结论/下一步：本次拼图工作流可作为当前仓库的结构交付；仍需真实题面、参数来源、独立复算和 Owner 审批后才可进入论文/群聊结论。

### 2026-09-01 · T-19 · MHAgent 结果包证据反推 Skill
- 目的：从用户提供的 MHAgent 赛题 A 导出包中复原可观察的七步能力链，并以旁路契约接入现有 Skill/拼图体系，不覆盖原有方法卡。
- 配置/数据：只读 `MHAgent_赛题A_全部_20260828_103359.zip`（本机源位置不入库）的 `README.txt`、`manifest.json`、阶段日志和产物清单；未复制题面/论文/数据/代码，未执行压缩包内脚本。
- 结果：新增 `skills/mhagent-evidence-reconstruction/`（入口、七步 JSON 契约、无依赖校验器）与 `docs/mhagent-reconstructed-workflow.md`；`skills/README.md` 仅新增索引。契约保留日志缺失、累积产物、checkpoint 未知、AUDIT fatal=2/warn=1、论文数据待 Claude 自检和 63/64 页漂移等未决项，状态为 `READY_FOR_REVIEW`。
- 验证：契约脚本 VALID；`python -X utf8 <CODEX_SKILL_ROOT>/skill-creator/scripts/quick_validate.py skills/mhagent-evidence-reconstruction` 通过；后端 `138 passed`；`node --check workflow-puzzle.js app.js` 通过；`python -m compileall -q backend skills/mhagent-evidence-reconstruction/scripts` 通过；`git diff --check` 通过。下一步：独立只读 Critic/Auditor 复核，关闭关键问题后再合并推送。

### 2026-09-02 · T-20 · LaTeX/PDF 实时编译器接入
- 目的：将论文编译接入现有任务抽屉、revision/CAS、事件流和 WebSocket，同时保持输入/产物边界可审计。
- 配置/数据：基线 `25f7782d6b80c60f316881c1d49deecc343bd074`；新增安全编译内核、编译器/API 测试、任务卡和接口文档；不向空的 `paper/` 写入示例论文。
- 结果：本机工具链探测实际跳过不可运行的 `latexmk`（Perl 缺失），选中可运行 XeLaTeX；Poppler `pdfinfo/pdftoppm` 可定位；专用编译器/API 测试 `13 passed`，后端全量 `151 passed`。日志脱敏覆盖混合分隔符与 TeX 跨行路径夹具；API 对入口不存在、绝对路径、越界路径同步拒绝。当前无 `paper/main.tex`，未生成伪造 PDF；独立 Critic 判定本地受信源 MVP `PASS`（P1=0）。
- 结论/下一步：已完成本地接入；生产部署仍需目标环境重新探测、staged source/OS 沙箱、持久化有界队列、OIDC/RBAC 与下载鉴权；编译成功不改变数学 claim 或 Owner 发布门。

### 2026-09-03 · T-21 · 校赛 B 题完整求解与论文交付
- 目的：用用户提供的 `校赛B题.docx` 与 `校赛B题附件.csv` 完成电信客户流失分析、判定、经济挽留和外部压力稳健性四问，并产出可复算论文与证据链。
- 输入锁定：DOCX SHA-256 `c2049336b8ef6d85ba5d52fc943d9deb839e8a4a20d083807cc7b267a0c96c89`；CSV SHA-256 `7131cd7542bc248f090e26e1beb40d22b9e9f1ec32d8c8854d71377a94b8d858`；CSV `gb18030`、7043 行、21 列、无重复客户编码，11 个结构性空总费用按 0 月规则处理；原始文件未入库。
- 实现：新增 `models/solve_b_problem.py`、`models/requirements-b.txt`、`paper/b_problem_contract.json`、`paper/b_problem_solution.tex`、12 页 `paper/b_problem_solution.pdf`、聚合证据/图表、`artifact_manifest.json` 与 `validation_results.json`。求解链为 Q1 关联画像 → Q2 Logistic/非线性对照/OOF 校准 → Q3 `p q L-C` 经济阈值 → Q4 显式 log-odds 压力和稳健下界。
- 结果：流失率 `0.265370`；Logistic 留出 AUC `0.842171`、五折 OOF AUC `0.845001`；经济阈值 `0.214286`，OOF 阈值策略 3286 人、期望净收益 `630184.63` 元；复合压力预测流失率 `0.338910`，稳健正收益集合 3122 人、下界和 `506335.09` 元。Q1/Q2 保持关联边界，Q4 保持 `HYPOTHESIS`。
- 系统修复：问题契约解析器覆盖 `问题 4`，并在显式问题标题存在时忽略 `(1)(2)(3)` 子项；能力建议器增加可解释领域别名和 `matched_terms`。新增回归测试 2 个。
- 验证：求解器 clean-run exit 0；论文契约严格审计 PASS（14 variables/11 equations/10 claims/14 crossrefs/8 checks）；LaTeX 数学审计 PASS（36 labels/20 refs）；XeLaTeX 双遍 exit 0、PDF 12 页 A4、全页视觉检查通过；后端全量 `153 passed`；服务端 E2E `runtime/solo-test/api_e2e_t21.py` PASS（题面 Q1–Q4、能力目录 13 blocks/54 methods、知识检索、路由预览、拼图组合、LaTeX job）。
- 结论/下一步：交付状态 `READY_FOR_REVIEW`，TASKS 标为待审；未自动合并/推送 main。官方投稿模板、匿名/页数规则、独立 Claude/Antigravity 数学复算和 Owner 发布审批仍待补齐。
