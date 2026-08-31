# 数学建模资料包：本地知识库接入方案

> 方案状态：Slice 0/1 已落地（只读 inventory、限量检索、短片段预览、群聊引用与 Agent context API）。原始资料保持在用户指定目录，系统只建立只读索引；任何“已验证”结论仍须通过题面、数据和复现门禁。

## 1. 已确认的资料边界

`C:\Users\zyy20\Desktop\数学建模资料全套包` 正在由同步客户端持续写入，数量会变化。以下是最近一次运行时快照（服务启动/`refresh=true` 时重扫；不是永久基线，时间以接口返回为准）：

| 指标 | 数量 |
|---|---:|
| 可检索文件 | 18,986 |
| 总容量 | 22.8 GB |
| 同步临时文件 | 1（禁止索引） |
| 来源状态 | `LOCAL_PENDING` |
| 索引 revision | 以 `GET /api/projects/{id}/knowledge/summary` 返回的当前 `index_revision` 为准 |
| 工程 source-only manifest | 见 `.collab/manifest.sha256`（随源文件变更重算） |

目录说明页中的“总文件/容量/PDF”是宣传性目录元数据，接口保留为 `catalog_claims` 但固定 `catalog_consistent=false`；系统以每次只读扫描为准，不把说明页数字写成事实。重扫后这些数字应以新 `index_revision` 和时间戳替换。

顶层目录已经提供了第一层分类：国赛、 美赛、研究生赛、其他赛事、模型算法与代码、论文写作与备赛、软件工具、课程资料、参考书库。分类器应优先继承目录，不应仅凭文件名猜测奖项或正确性。

## 2. 总体架构

```text
原始目录（只读）
   │ 已落地：inventory（路径、大小、mtime/ctime/inode、类型）
   ▼
抽取队列 ── PDF文本/OCR、DOCX/PPTX/表格、代码文本
   │
   ▼
规范化文本 + 页/段/表格坐标 + 分类置信度
   │
   ├─ SQLite：documents/chunks/aliases/ingest_jobs + FTS5
   ├─ 可选向量索引：仅对已抽取文本，保留 chunk_id 映射
   └─ append-only ingest journal：每次索引快照与错误
   │
   ▼
已落地：KB Adapter（只返回最小证据包；prompt-sized context）
   │
   ▼
已落地：群聊引用卡片、路线对照、证据预览（Owner 才能打开原文件）
```

当前实现先在进程内保存 metadata snapshot，默认 60 秒 TTL；不复制原件。生产切片应把同一记录落到项目外的 `runtime/knowledge_base/`（已被 `.gitignore` 忽略），再接 SQLite WAL/FTS5 和可恢复抽取队列。

## 3. 资料如何转化为可泛化的建模能力

“吸收资料”在本系统中不是把 2 万余份文件一次性喂给某个模型，也不是把往届范文的答案套到新题；它是一个可追溯的四层投影：

| 层 | 从资料中保留什么 | 输出 | 能否直接作为事实 |
|---|---|---|---|
| 来源层 | 路径、格式、时间、哈希/抽取状态、短片段 | `documents`、`kbdoc` | 仅能证明来源元数据 |
| 内容层 | 题面句子、变量/目标/约束/验证线索、写作结构 | 受限 context、方法卡字段 | `OBSERVED`，仍需回原文核对 |
| 能力层 | 方法适用域、输入/输出端口、禁用条件、验证要求、所需 Agent 角色 | `workflow_blocks`、`methods`、预设/题型 archetype | 只表示候选能力，不证明本题适用 |
| 运行层 | 当前题面的契约、选中的 DAG、运行日志和独立复核 | `problem_contract`、`assembly`、`evidence_refs` | 只有复现/审查后才可升级 claim |

能力目录由当前索引快照投影而来，使用 `capability_revision` 绑定来源；当前 MVP 已提供内置方法卡、工作流块、预设、题型 archetype 和五个一等内容包。方法卡/内容包目前是 `curated/inferred` 编排能力，只有在内容包 resolve 返回真实 `kbdoc` 证据、且经过题面与独立验证后，才可升级为本题可用证据。它们应保留 `source_refs`、`claim_class`、`applicability`、`prohibitions`、`validation_checks` 和覆盖状态。目录命中分数不等于适配分数，更不等于优越性证明。

### 3.1 动态题面契约

`POST /api/projects/{id}/capabilities/problem-contract` 对任意中文/英文题面做保守抽取：编号小问、交付动词、变量线索、约束线索、数据线索、验证线索和题型 cue。字段携带 `claim_class=observed` 与 `evidence_refs`；archetype 推荐携带 `claim_class=hypothesis`。接口返回 `status=DRAFT_UNVERIFIED` 和确定性 `sha256:<64 hex>` revision。

它不负责理解隐含语义、确认单位、判定题目真实机制或替代人工读题。没有明确编号时会生成一个 `Q1` 草稿；这只是 UI 的起点。Scope-Lock 必须在后续覆盖表中逐句确认小问、附件、范围和交付物，才能进入路线设计。

### 3.2 标准工作流、自由装配与硬门

标准预设为常见 archetype 提供可审计的默认 DAG；自由装配允许使用者从 `workflow_blocks`、`methods` 和 `content_packs` 中选择节点，并用严格类型端口连接。系统目前固定四个产品硬门：

`problem-decomposition → baseline-model → validation → writing`

参数/约束契约、场景契约和 `critic-challenger` 是可插拔扩展。服务端只验证引用、端口类型、必需输入、无环性以及模型→验证→写作的证据链，不执行外部模型、代码或原始资料。自由装配可以改变节点、方法和配置，但不能绕过硬门；题型专属节点可以增加，不能伪造覆盖率。

每次装配生成 `assembly:<64 hex>`。提交前与上一版对比，形成 `assembly-diff/v1`：新增/移除/修改节点、边变化、受影响节点、缺失硬门和 `claim_class=derived`。差异是审计事实，不是创新性结论；所谓“创新”必须另有可验的假设差异、机制差异、数据证据、消融/敏感性或复现实验支持。

### 3.3 内容包的使用规则

内容包目前作为能力目录中的一等对象，用 `content_pack_ids` 挂载到装配；同时可通过只读 `GET /api/projects/{id}/capabilities/content-packs/{pack_id}/resolve` 按固定查询词解析当前资料快照。它用于把资料中的可迁移结构拆成最小单元，例如“变量—目标—约束字段”“预测题独立回测清单”“优化题可行性/敏感性检查”“论文三线表/图表说明模板”。resolve 返回的文档级 `kbdoc` 是候选证据，不是页级引用或结论。每次使用仍应记录：

1. 该包解决哪个小问和哪个接口问题；
2. 使用了哪些 `kbdoc` 与 `capability_revision`；
3. 哪些内容是资料原文、Agent 推断或待验证假设；
4. 如何通过当前题目的数据、反例、独立路线或 clean-run 验证。

装配事件同时记录 `content_pack_ids`、`content_packs`、`content_pack_evidence_refs`（若已解析）和 `capability_revision`；内容包的挂载/卸载会改变装配 hash，并进入 `assembly-diff/v1`，避免群聊只看到一句不可回放的“已吸收资料”。

因此，“资料被系统吸收”的验收标准是可追溯、可组合、可回放和可验证，而不是目录文件被计数或模型回复看起来像范文。

## 4. 索引数据模型

### 4.1 文档级 `documents`

```yaml
doc_id: kbdoc_<sha256前16位>
path_rel: 01_国赛资料模块/历年赛题与获奖论文_按年份/2019/B047.pdf
root_id: math-modeling-pack
source_status: LOCAL_INDEXED        # LOCAL_INDEXED/LOCAL_PENDING/SOURCE_CHANGED/UNAVAILABLE
content_class: user_private         # user_private/official_public/licensed_unknown/restricted
mime: application/pdf
extension: .pdf
size_bytes: 1234567
mtime_ns: 0
ctime_ns: 0
inode: 0
sha256: sha256:<64 hex>             # 大文件默认按需；可能为 null
hash_status: INLINE|DEFERRED|DEFERRED_LARGE|INLINE_ON_DEMAND
text_sha256: sha256:<normalized text hash>
duplicate_of: null                  # exact/near duplicate 时指向 canonical doc_id
title: 2019 B047（文件名推断）
contest: CUMCM                          # path-derived, confidence=0.98
year: 2019                              # path-derived, confidence=0.99
problem_code: B047                      # filename-derived, confidence=0.80
award_level: unknown                    # 未明确写出时不得推断
language: zh
page_count: 0
extractor: pymupdf|pdfplumber|ocr|docx|text
extract_status: TEXT_EXTRACTED|TEXT_PARTIAL|OCR_REQUIRED|PREVIEW_UNAVAILABLE|REINDEX_REQUIRED
classification_confidence: 0.0-1.0
created_at/indexed_at: ISO-8601
```

### 4.2 片段级 `chunks`

```yaml
chunk_id: kbchunk_<doc_id>_<seq>
doc_id: kbdoc_...
seq: 12
page_start: 4
page_end: 5
heading_path: [问题分析, 模型假设]
kind: prose|formula|table|figure_caption|code|notice
text: 规范化后的片段（保留公式占位和表格行）
text_sha256: sha256:...
char_start: 1820
char_end: 2650
fts_tokens: ...
embedding_ref: null                    # 向量索引启用后填写
quality: native_text|ocr_low|manual_check
```

目标数据模型的片段必须始终能回到 `doc_id + page_start/page_end + char offsets`。当前 Slice 0/1 对外稳定承诺的是文档级 `kbdoc:<doc_id>` 和受限短片段；PDF 页级 `kbchunk`/OCR 坐标仍属于 Slice 2，不在当前结果中伪装成已完成。

### 4.3 受控标签 `tags`

标签分三类并分别记录来源：

1. `path`：目录推断（如 `contest:cumcm`、`module:papers`）。
2. `filename`：文件名正则（如 `year:2019`、`problem:B`）。
3. `content`：文本识别（如 `topic:optimization`、`model:logistic`），必须带 `confidence` 和命中片段。

标签只能帮助检索，不能自动变成论文事实。规则通知和真实题面优先级高于获奖论文中的叙述。

## 5. 扫描、抽取与去重策略

### 5.1 扫描与增量

* 只允许访问配置根目录；规范化后拒绝 `..`、符号链接、挂载到根目录外的路径。
* 首次扫描先写 inventory，不抽取全文；按文件大小、类型和目录生成可恢复队列。
* 当前增量/快照指纹至少包含 `path_rel + size_bytes + mtime_ns + ctime_ns + inode + sha256/hash_status`。大文件默认不在首扫全量哈希，故当前 revision 是 metadata snapshot，不是内容冻结证明；显式打开大文件也会保持 `DEFERRED_LARGE`，避免阻塞。
* `.qkdownloading`、临时文件、密码保护无法读取的文件进入 `REJECTED/SKIPPED`，保留原因。
* ZIP/RAR 不自动解压到工作区；若 Owner 明确批准，解压到隔离临时目录并重新走路径和大小限制。

### 5.2 编码与文本

* 纯文本优先尝试 UTF-8（含 BOM）、GB18030、Big5，再以替换字符比例判断质量；原字节 SHA 永远保留。
* PDF 优先 PyMuPDF/pdfplumber 原生文本；每页保存页码标记。原生文本为空或乱码比例高时标记 `ocr_required`，再进入 OCR 队列。
* OCR 结果必须标注 `quality: ocr_low`，数字、单位、负号、小数点、公式变量进入低置信度清单；不得覆盖原始 PDF 文本。
* DOCX/PPTX/XLSX 仅在压缩包大小和解压总量上限内按需抽取；旧式 DOC/PPT/XLS 只做元数据候选，避免把二进制误当文本。
* `.m`、`.py` 等代码仅做静态文本索引，禁止导入、执行或安装其中依赖。

### 5.3 片段与检索

* 先按章节标题、页、表格和代码函数切分，再对长段按 500–1,000 个中文字符切分，重叠约 80 字；公式和表格不可从中间截断。
* SQLite FTS5 作为必选离线检索；向量检索是可选增强，不得成为唯一入口。混合排序建议 `0.65 × lexical + 0.35 × semantic`，并对标题、题号、年份、目录标签加权。
* 精确 SHA-256 去重；规范化文本做 SimHash/MinHash 近重复检测（阈值写入索引配置）。canonical 优先级：原生文本 > OCR、路径信息完整 > 信息不全、较新版本 > 旧副本。所有别名保留。

## 6. API（当前离线开发版）

现有消息 API 现在接受严格格式的 `kbdoc:kbdoc_<16位hex>`（以及预留的 `kbchunk`）引用，但不能放宽现有发布门禁；artifact/release gate 仍要求真实 manifest、结果 hash 和独立验证。

### 状态与索引

```http
GET /api/kb/status
```

实际提供 `GET /api/projects/{project_id}/knowledge/summary` 与别名 `GET /api/kb/status`，返回 `root_id`、`root_label`、`index_revision`、`indexed_count/valid_count`、`pending_count`、`rejected_count`、字节数、facets、`last_scan_at`、`source_status`、`hash_policy` 和目录宣传数字警告。摘要默认不携带完整文件清单。

当前没有后台 OCR/全量抽取 job；`refresh=true` 是 Owner 明确触发的同步扫描。后台可恢复队列、暂停/重试和 OCR 属于 Slice 2，不能在当前界面宣称已完成。

### 搜索与分类

```http
GET /api/projects/{project_id}/knowledge/search?q=约束+敏感性&year=2019&module=...&kind=...&extension=pdf&top_k=8&with_preview=true
GET /api/projects/{project_id}/knowledge/retrieve?...       # Agent 检索别名
GET /api/projects/{project_id}/knowledge/context?...         # prompt-sized context
GET /api/projects/{project_id}/knowledge/documents/{doc_id}
GET /api/projects/{project_id}/knowledge/documents/{doc_id}/file
```

搜索响应包含 `query`、`index_revision`、`results[{doc_id,title,path_rel,snippet,extract_status,hash_status,score,tags,source_status,citation_ref}]`、`total_candidates`、`returned_count`、`truncated`、`warnings`。默认 `top_k<=20`，正文抽取最多检查有限候选，摘要/预览有字符上限；全文读取必须二次请求。打开前会做 size/mtime/ctime/inode 新鲜度检查，发生变化返回 `KB_SOURCE_CHANGED`，大文件哈希保持 `DEFERRED_LARGE`。

### Agent 工具调用

Orchestrator 给 Agent 的工具只有：

```json
{
  "name": "kb.search",
  "input": {"query":"2019 B题 约束建模", "filters":{"contest":"CUMCM","year":2019}, "top_k":6},
  "output": {"index_revision":"kb:<64hex>", "items":[{"doc_id":"kbdoc_...", "snippet":"...", "citation_ref":"kbdoc:kbdoc_..."}], "evidence_refs":["kbdoc:kbdoc_..."]}
}
```

Agent 不获得任意路径读取权。每个群聊结论可挂载文档级 `kbdoc` 引用，并区分 `OBSERVED`（资料原文）、`INFERRED`（Agent 推断）和 `HYPOTHESIS`（待验证建议）；页码级 `kbchunk` 只有在 Slice 2 完成后才能启用。

## 7. 群聊前端交互

1. 输入框支持直接输入 `@知识库 关键词`；也可在右侧选择“搜范文/搜算法/搜规则/搜模板”和年份/模块筛选。
2. 右侧资料库卡显示查询、返回数/候选数、索引 revision、`LOCAL_INDEXED/LOCAL_PENDING` 状态和限流警告。
3. 当前引用是文档级 chip：`kbdoc:kbdoc_<16位hex>`。点击先打开受限只读片段预览；再次由 Owner 点击才打开本地原文件。页码/段落 chip 等 OCR 能力尚未冒充上线。
4. 右侧资料库面板显示索引快照、同步数、容量和目录 facets；“重扫”明确不会修改原始资料。
5. 若无题面或索引不完整，Agent 只能说“资料建议/待复核”，不能把范文模型直接套成当前题目的答案。路线 A/B 对比卡应显示各自引用覆盖率和 OCR 低质量警告。

推荐的群聊快捷语：

* `@知识库 搜 2016–2025 国赛 B题 中“敏感性分析”的写法，返回页码和原文定位。`
* `@知识库 给 Q3 的两条候选路线各找 3 篇不同年份范文，只提取变量—目标—约束字段。`
* `@知识库 检查当前模型假设是否在资料中有反例；没有证据时标记 UNVERIFIED。`

## 8. 安全、隐私与版权边界

* 默认 `local_only=true`：不把原始文件、全文片段或路径发送给 Antigravity、Claude、Qoder、云端模型。跨 Agent relay 只发送 Owner 批准的最小片段、哈希和引用。
* API 只返回根目录下的相对路径；日志不记录完整用户名路径。拒绝目录逃逸、外链、同步临时文件和不安全 Office 压缩包；原始大文件只能在 Owner 明确点击后以内联方式打开，当前仍是 localhost 离线开发边界。
* 文档按 `content_class` 分级。`user_private`/`licensed_unknown` 的内容只能在本机索引和引用；`restricted` 禁止外发。该标记是工程控制，不是对授权状态的法律认定。
* 不批量导出整篇范文、教材或代码；回复只给必要短摘录、页码和文件名，优先总结而非大段复制。正式论文引用由 Owner 再核对原件和许可。
* OCR、分类和模型建议均不是事实认证；界面必须显示“资料来源/抽取质量/最后索引 revision”。summary 还应显示全量索引与可正文抽取覆盖率，避免把“已索引”误读成“已理解”。

## 9. 验收测试

### 最小自动化门禁

* inventory 文件数、扩展名分布和总字节数与本次扫描快照一致；所有同步临时后缀均未入库。
* 文档 metadata revision 可回溯到 size/mtime/ctime/inode；大文件 hash 明确为 deferred，不把 metadata 当内容冻结。
* 用已知文件名、年份、题号、模型词和中文/英文混合词搜索，命中结果的 `source_status`、抽取状态和文档级 citation_ref 完整；页码/chunk 仍待 Slice 2。
* 原生 PDF、扫描 PDF、GB18030 文本、DOCX 表格各有一条回归样本；OCR 低置信度、乱码/空文本和像素矩阵误读会显示警告。
* 断点续扫后计数不丢失；索引损坏或 revision 不匹配时 API 返回 `UNAVAILABLE/REINDEX_REQUIRED`，不伪造结果。
* Agent 无法读取未声明路径；搜索结果摘要超长、结果超过 top_k、外部 relay 未审批均被拒绝。
* 所有 KB 引用在群聊、任务详情、证据预览中保持相同 `kb:<64hex>` revision；搜索响应明确区分 metadata candidates、正文检查数和返回数；引用格式合法不等于来源存在，release 前仍需 artifact/provenance/validation gate；旧 revision 只能只读，不能写入当前论文 claim。

### 人工抽查（首轮至少 30 份）

按模块各抽 3–5 份，检查标题、年份、题号、页码、公式负号/单位、表格表头、近重复归并和引用是否能在原文件中定位。抽查记录存 `.collab/evidence/KB-<run_id>/`，不把整本原件复制进仓库。

## 10. 最小可交付切片（建议顺序）

### Slice 0：只读 inventory（已完成）

配置根目录、扫描并生成 `inventory.jsonl`、SHA-256、扩展名统计、失败清单和 `GET /api/kb/status`。不抽取全文、不调用模型，先证明边界和隐私设置正确。

### Slice 1：受限 metadata/短片段检索（当前已完成的 MVP）

已覆盖国赛范文、规则通知、模型算法、论文写作等目录；完成 PDF/DOCX/文本的按需短片段抽取、`/api/kb/search`/`context`、前端 `@知识库` 检索卡和文档级引用预览，并提供内容包 resolve 的候选证据绑定。当前不承诺全量 FTS5、页码 chunk、OCR 或语义向量。

### Slice 2：全量可恢复索引（2–5 天，取决于 OCR）

后台队列覆盖当前扫描中尚未抽取的文件（数量随同步盘面变化）；OCR 和大书分批、可暂停、可重试。加入页级 chunk、近重复检测、facets、索引版本和清单审计；向量索引作为可选增强。

### Slice 3：建模工作流绑定（能力层 MVP 已落地）

已加入能力目录、方法卡/工作流块/题型 archetype、动态题面契约、标准预设与自由 DAG 装配。装配校验会强制四个产品硬门、类型端口和模型→验证→写作证据链；提交时以 `ASSEMBLY_UPDATED` 追加事件并保留差异审计。资料建议仍必须携带 `evidence_refs` 和来源状态，不能直接升级为 `READY_FOR_REVIEW` 或论文 claim。

### Slice 4：全链路题目绑定与执行

把每个小问的 context packet、方法卡和 `kb.search` 结果接入真实 Solver/Validation/Paper Agent，强制参数/单位/边界条件和 clean-run 证据；先做离线 replay 与盲审，再允许任何资料建议进入 `READY_FOR_REVIEW`。这一步尚未由当前本地 MVP 自动完成。

### 当前回归证据（2026-08-31）

```text
node --check app.js                         PASS
python -m compileall -q backend             PASS
python -m pytest backend -q                 预计 87+ passed（以当前 checkout 实测为准）
能力目录/装配/题面契约回归                 PASS（与现有 API 合计）
真实资料盘 summary                          18,986 文件 / 22.765 GB / 1 临时文件；可正文抽取覆盖率以 summary.extractability 为准
带短预览检索（目录命中）                    约 0.4–2.2 秒（随盘面与缓存变化）
```

上述数量和耗时是运行时观测，不是资料包永久承诺；服务重启或 `refresh=true` 后可能变化。

## 11. 与 Agent 分工的默认路由

| Agent | 知识库职责 | 禁止事项 |
|---|---|---|
| Scope/规则 | 官方通知、赛题原文、格式约束 | 用范文推断本届规则 |
| Data Auditor | 数据模板、字段字典、缺失/异常处理范例 | 把示例数据当真实附件 |
| Route-A | 机制/优化路线范文和算法模板 | 复制结论而不重建变量与约束 |
| Route-B | 统计/仿真路线、基线和敏感性范例 | 用单一范文证明模型优越 |
| Critic/Challenger | 反例、失败模型、验证章节 | 只按检索分数否决方案 |
| Paper/Release | 引用定位、排版模板、检查清单 | 输出未审计的全文复制 |
| Owner（你） | 批准索引、外发、引用和最终采用 | 将 Agent 评分当作审批 |
