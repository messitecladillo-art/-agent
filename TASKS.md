# 任务看板

> 任务的唯一事实来源。开工前 `git pull` 读本文件；认领/完成/评审后**立即更新并提交**。
> 状态流转：待认领 → 进行中 → 待审 → 已完成。任务编号格式 `T-<序号>`。

## 进行中

（暂无）

## 待认领

| ID | 任务 | 优先级 | 验收标准 |
|---|---|---|---|
| T-02 | 配置本地 Python 环境与 `.env` | 高 | `pip install anthropic` 成功，`.env` 含有效 KEY |
| T-03 | 跑通独立评审脚本 | 高 | `python scripts/agents/review.py README.md` 生成评审报告到 `notes/reviews/` |
| T-04 | 在 Codex 中绑定 GitHub 仓库 | 高 | 能从 Codex 对该仓库派发云端任务 |
| T-05 | 用 Antigravity 打开本目录 | 中 | 工作区正常，能读取 AGENTS.md |
| T-07 | 按 `notes/exemplary-paper-breakdown.md` §3 建立算法模板库 | 高 | 评价/优化/预测/分类/机理/仿真每类至少 1 个可运行模板，放入 `models/` |
| T-08 | 确定论文模板与图表规范 | 中 | 国赛 LaTeX / 美赛 COMAP 模板进 `paper/`，图表规范进 `viz/` |

## 待审

| ID | 任务 | 交付/复核状态 |
|---|---|---|
| T-22 | 删除旧技能并按资料包重建可组合的数学建模 Skill v2（注册表、契约、校验器、固定/DYI/备赛流程、后端目录接口） | `READY_FOR_REVIEW`；16 个入口、86 张方法卡、12 个来源、完整回归通过，等待 Owner/独立评审确认 |
| T-21 | 校赛 B 题完整求解与论文交付（Codex solo） | `READY_FOR_REVIEW`；等待 Owner/独立评审确认 |

## 已完成

| ID | 任务 | 完成日期 |
|---|---|---|
| T-18 | 固定方案 + DIY 工作流拼图工作台（小青龙 ImageGen 资产、类型方法卡、实时目录同步与双模式验收） | 2026-09-01 |
| T-14 | 融合建模议事厅前端与青甲骨刻体字体（参考板式、许可证、源数据与回归验收） | 2026-09-01 |
| T-15 | 按 QQ/微信群聊范式重排消息流（左右对齐、连续消息分组、系统消息居中、附件安全卡） | 2026-09-01 |
| T-11 | 核心资料导入 QMind 知识库（Notebook「数学建模」：12 份官方评阅标准 + 拆解/索引文档 + skills 共 24 源，检索验证通过；2024 评阅要点为文本摘要版） | 2026-08-31 |
| T-01 | 创建 GitHub 私有仓库并绑定远端（`origin` → `messitecladillo-art/-agent`，main 已推送，凭据经 Git 凭据管理器建立） | 2026-08-31 |
| T-00 | 初始化项目骨架与团队守则 | 2026-08-31 |
| T-06 | 拆解近十年模范论文并总结（产物：`notes/exemplary-paper-breakdown.md`） | 2026-08-31 |
| T-09 | 盘点桌面资料包并建索引（产物：`notes/materials-index.md`） | 2026-08-31 |
| T-10 | 夸克网盘补全下载（用户完成；验证：18,987 文件、无残留未完成项） | 2026-08-31 |
| T-12 | 精读 2021/2023/2024 官方评阅要点，升级拆解文档 §4（官方总则+分题型信号+五条金律） | 2026-08-31 |
| T-13 | 建立 skill 库与比赛 workflow（产物：`skills/` 7 个阶段 skill + 2 条 workflow；review.py 挂钩评审准则） | 2026-08-31 |
| T-17 | 从校赛一等奖论文提炼数学表达与排版 Skill（推导链、公式/符号/图表/复现门；含结构审计与前向夹具） | 2026-09-01 |
| T-19 | 从 MHAgent 赛题 A 结果包反推可复用 Skill 与证据契约（旁路七步契约、校验脚本、迁移说明与独立只读复核） | 2026-09-01 |
| T-20 | 配置 LaTeX/PDF 实时编译器与可观察状态（安全入口/产物边界、工具链探测、事件流/API、任务抽屉卡片） | 2026-09-02 |

## 远端 main 同步记录（origin/main@ffd6001）

为避免与本地 UI 任务使用相同编号产生歧义，远端已完成内容按来源单独保留：

- 资料深挖五路回灌（历史记录；旧入口已在 T-22 重建）：美赛增量、`notes/算法模板盘点.md`，以及 Skill 01–06 与 workflow 的逐年评阅证据、2010B 评分细则、格式规范和常见失分点。
- QMind 知识库导入：12 份官方评阅标准、拆解/索引文档与 skills 共 24 源已完成检索验证；2024 评阅要点以文本摘要版入库。
- 远端骨架任务：T-02/T-03（本地 Python 与独立评审脚本）、T-04/T-05（工具接入）、T-07/T-08（算法模板与论文/图表模板）仍保持待认领状态，等待实际负责人和可复现证据。

本地 T-14/T-15 记录的是议事厅前端与群聊信息流，和上述远端资料任务并列存在；本地新增任务从 T-17 起编号。

## v12/v13 设计验收记录

| 主题 | 约束 | 验收证据 |
|---|---|---|
| 浮动纸面壳 | 暖白纸面、低对比度青玉线、短软阴影；消息/公式/证据不使用透明玻璃 | `docs/ui-system.md` §8 |
| 青甲骨字体 | 仅品牌、首屏短标题、短印记；正文、表格、状态和审计字段不用展示字体 | `docs/fonts/qingjia/` 与 `docs/ui-system.md` §8 |
| 群聊层级 | 当前 Q/阶段/阻断/Owner 常驻；正文优先；provenance 默认收起但一键可达 | `docs/ui-system.md` §9 |
| 移动抽屉 | <850px 左栏折叠，聊天区单列，任务/证据右抽屉不造成零宽或横向溢出 | `docs/ui-system.md` §9 |
| 浏览器回归 | 1440×900、1024×768、768×1024、390×844、360×800；无横向溢出、消息对齐正确、抽屉 tab 不溢出 | `experiments/log.md` v12/v13 记录 |

## v13.2 质感增量验收记录

| 项目 | 验收要求 | 记录位置 |
|---|---|---|
| 左侧小青龙水印 | 低对比度、不可遮挡文字与交互，不承担功能语义 | `docs/ui-system.md` §10 |
| 主视觉 | 首屏可见但不承载事实；当前 Q、阻断和路线摘要优先 | `docs/ui-system.md` §10 |
| 角色识别 | 角色色带 + 文字状态点双重表达，不能只靠颜色 | `docs/ui-system.md` §10 |
| Overview 压缩 | 保留 Q/阶段/路线/验证，长字段进入控制面或 provenance | `docs/ui-system.md` §10 |
| 字体回退 | QingJia 加载失败时布局稳定、正文可读、私用区不裸露 | `docs/ui-system.md` §10 |
| 回归 | 后端 95 tests；1440×900、1024×768、768×1024、390×844、360×800 无横向溢出 | `experiments/log.md` v13.2 记录 |

## v13.5 触感层级验收记录

| 项目 | 验收要求 | 记录位置 |
|---|---|---|
| 纹理边界 | 聊天纹理仅作边缘纸面氛围，中心正文保持可读 | `docs/ui-system.md` §11 |
| 右栏层级 | 当前运行卡保留浮层重量；普通任务/证据行无常驻阴影，hover 才抬升 | `docs/ui-system.md` §11 |
| Toast 安全带 | 移动端 prepare/show 均预留 56px；提示不覆盖最后气泡或 composer | `app.js` `showToast()` 与 `styles.css` v13.4.1 |
| 多视口 | 1440×900、1024×768、768×1024、390×844、360×800 无横向溢出，消息/阶段/字体可读 | `experiments/log.md` v13.5 记录 |
| 移动抽屉清晰度 | 遮罩低于抽屉；抽屉正文不受自身 backdrop-filter 模糊；背景仍柔和压暗 | `experiments/log.md` v13.5.3 记录 |

## T07-R workspace catalog / v14 文档口径（附加切片）

| 项目 | 口径 | 验收位置 |
|---|---|---|
| 仓库挂载 | 只读 allowlist：README/TASKS/AGENTS + app/index/styles/docker + backend/assets/docs/skills/notes/workflows/models/paper/viz/scripts/experiments；排除 secrets、runtime、.collab、链接与绝对路径 | `backend/README.md`、`docs/api-contract.md` §10 |
| source_integrity | `observed` 只证明路径边界、读取行为和 manifest 可审计，不证明内容正确、授权或题面适配 | `docs/knowledge-base-integration.md` §12 |
| repo 引用 | `repo:<relative-path>` 可作为候选指针保留在 `evidence_refs`，但不得单独升级为 kbdoc/VERIFIED/论文 claim | `README.md` §12、`docs/api-contract.md` §10.1 |
| v14 质感原则 | 连续暖纸面、局部玻璃、单一主浮层、安静任务清单、触感反馈不喧闹；保持多视口与安全带验收 | `README.md` §13、`docs/ui-system.md` §12 |
| 真实运行限制 | offline-dev、进程内 journal、无默认真实模型/RBAC/签名 relay；状态必须显式标识 | `backend/README.md`、`docs/ui-system.md` §12.2 |

## v14.2.13 最终回归记录

| 主题 | 验收证据 |
|---|---|
| 触感层级 | 暖纸面连续承载；消息/证据近不透明；单一主浮层；成功连接提示由顶栏状态承载，不再遮挡右栏 |
| 宽屏临界 | 1321/1340/1350/1360/1366/1440×900：聊天气泡不与 feed 上下边界相交，masthead 三轨无几何重叠 |
| 低高度桌面 | 1280/1366/1440×720 与 1024×720：hero/Q 收束为单行定位层，聊天区保留至少两条完整近期消息 |
| 平板/短屏 | 1024/1180/1280×768：无横向溢出，首个可见气泡完整，Q 轨可读 |
| 手机 | 390×844、360×800：Q 轨单行编号/状态，气泡与 composer 不相交，抽屉遮罩 z10 / 面板 z20 |
| 工程挂载 | workspace catalog 86 项、67 项可检索、13 项视觉资产；`skills` 检索返回24项；越权路径返回400 |
| 代码与测试 | 后端 `100 passed`；Python compileall、Node syntax、CSS 花括号计数均通过；密钥与大文件扫描无命中 |
| 运行边界 | 本地 API 仍为 offline-dev；运行时 manifest 以当前 allowlist 计算，忽略旧 `.collab` 声明并显式标记 `STALE_DECLARATION` |

---

## 任务模板（复制使用）

```
| T-xx | <一句话任务> | 高/中/低 | <可检查的验收标准> |
```
