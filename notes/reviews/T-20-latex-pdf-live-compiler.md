# T-20 LaTeX/PDF 实时编译器独立复核

- 审查身份：`codex/latex-critic`（只读 Critic），协调者：`Codex`
- 输入 revision：`git:25f7782d6b80c60f316881c1d49deecc343bd074`
- 目标 revision：T-20 工作树（待合并提交）
- 审查结论：`PASS`，范围限定为“本地受信源 MVP”；P0/P1 均为 0。

## 已验证

- 编译器/API 专用测试：`13 passed`；后端全量：`151 passed`。
- `python -m compileall -q backend`、`node --check app.js`、`node --check workflow-puzzle.js`、`git diff --check` 均退出码 0。
- 当前机器的可运行工具链为 MiKTeX XeLaTeX；`latexmk` 因 Perl 缺失被版本探测跳过，Poppler `pdfinfo/pdftoppm` 可用。
- 真实临时 XeLaTeX smoke 生成 1 页 PDF，`pdfinfo` 可读页数/大小，SHA-256 已记录；没有向仓库空的 `paper/` 写入示例论文。
- 同一幂等键的重试保持同一 job-id，返回 `202` 且不会重复启动；事件按 `QUEUED → RUNNING → FINISHED/FAILED` 投影到 EventStore/WebSocket。
- 入口、符号链接、输出目录、PDF `%PDF-`/`%%EOF`、大小上限、固定 argv、`shell=False`、`-no-shell-escape`、超时和 bounded 日志均有实现/测试。
- `_redact_log` 已覆盖混合 Windows/POSIX 分隔符与 TeX 在路径组件内插入换行的夹具，避免把仓库、runtime、引擎绝对路径直接返回浏览器。

## 保留的 P2 运营项

1. 轻量 PDF 签名校验不等于完整 PDF parser；正式发布前仍需 `pdfinfo` 成功返回码、解析器和 render QA。
2. 当前是单进程有界任务；公网/多租户前需 OS/容器沙箱、低权限账户、网络禁用、资源配额和出站文件审计。
3. runtime 遗留清理依赖有限内存历史；生产需启动扫描、TTL、磁盘配额和持久化队列。
4. 目标服务器必须重新探测 XeLaTeX/Poppler，不要由 requirements 自动安装 TeX/Perl。

这些 P2 不阻止本地受信源 MVP 接入，但在公网发布或把结果标成正式论文 artifact 前必须重新审计并关闭。
