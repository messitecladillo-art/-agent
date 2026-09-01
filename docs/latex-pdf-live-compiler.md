# LaTeX/PDF 实时编译器（T-20）

本功能把论文编译接入现有的任务抽屉和事件流。它是“显式点击触发的有界任务”，不是按每次输入自动执行的 watcher，也不会把编译成功误标成数学结论或发布批准。

## 入口与状态

前端运行在 `http://127.0.0.1:8787/?live=1` 时，右侧“任务”面板出现“LaTeX · PDF 实时编译”卡片。入口文件默认是 `paper/main.tex`，必须由 Owner 明确点击“编译”。状态按以下顺序投影：

```text
工具链探测 → QUEUED → RUNNING → SUCCEEDED / FAILED / TIMED_OUT / UNAVAILABLE

如果终态记录已经因有限历史淘汰，重复幂等请求返回 `EXPIRED`，不会重新启动编译进程。
```

当前仓库的 `paper/` 只有 `.gitkeep`，因此没有默认论文入口；界面应显示入口缺失或工具链状态，不创建示例论文、不伪造 PDF。

## API

```text
GET  /api/projects/{project_id}/latex/toolchain
POST /api/projects/{project_id}/latex/compile
GET  /api/projects/{project_id}/latex/jobs/{job_id}
GET  /api/projects/{project_id}/latex/jobs/{job_id}/pdf
```

编译请求示例：

```json
{
  "entrypoint": "paper/main.tex",
  "compiler": "auto",
  "engine": "auto",
  "clean": true,
  "base_revision": "manifest:<64 hex>",
  "idempotency_key": "latex-<client-generated-id>"
}
```

工具链接口只返回可用性、编译器名称和候选名称；不会把服务器上的绝对可执行文件路径返回给浏览器。

入队前会检查项目 ID、`base_revision` 和入口文件。入口必须是仓库内 `paper/`、`models/` 或 `artifacts/` 下的 `.tex` 相对路径；绝对路径、`..`、非 `.tex`、不存在文件和符号链接均拒绝。成功响应为 `202`，并返回 `job_id` 和 `LATEX_COMPILE_QUEUED` 事件。相同幂等键重试会复用原 job，不启动第二个进程。

## 编译边界

- 工具链按“可执行且 `--version` 成功”探测，优先 `tectonic`，其次可运行的 `latexmk`/XeLaTeX/LuaLaTeX/pdfLaTeX。PATH 中存在但不能启动的 `latexmk`（例如缺 Perl）会被跳过。
- 命令使用固定参数、固定仓库 `cwd`、`shell=False`、非交互模式、超时和最大日志字节数。直接 XeLaTeX 使用 `-no-shell-escape`。
- 返回日志会对 repo/runtime/引擎路径做大小写不敏感、混合分隔符和 TeX 跨行组件脱敏；完整原始日志不通过浏览器接口暴露。
- 每个 job 只写 `runtime/latex/<job_id>/`，日志和 PDF 均不进入 Git；API 保留有限历史并在淘汰终态 job 时清理其运行目录；PDF 下载必须经过 job 状态和路径白名单检查。
- 成功 PDF 计算 `sha256`，并尽量用 `pdfinfo` 读取页数/字节数；缺少 Poppler 时保留 hash，但页数/视觉 QA 为未知。
- 事件先写入 EventStore，再通过现有 WebSocket 广播：`LATEX_COMPILE_QUEUED`、`LATEX_COMPILE_STARTED`、`LATEX_COMPILE_FINISHED` 或 `LATEX_COMPILE_FAILED`。

## 运行与部署

本机开发：

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8787
```

目标服务器必须重新执行工具链探测；Windows 主机上的 MiKTeX 不会随 Python requirements 或 Docker 镜像安装。不要在生产环境自动安装 TeX/Perl/Poppler。当前 runner 是单进程 `asyncio.create_task`，服务重启后 job 状态不恢复；多 worker、公网访问前必须替换为有界持久化队列、真正的文件/进程沙箱、OIDC/RBAC、下载鉴权和审计存储。

## 与数学建模发布门的关系

编译成功只说明 TeX 引擎生成了一个可读取的 PDF。它不代表公式正确、参数有来源、结果可复算、claim 已 VERIFIED，也不跳过 `artifact_manifest → render_qa → independent review → Owner approval`。正式论文仍需使用 `skills/math-modeling-mathematical-writing/` 的数学表达、结构审计和 PDF 视觉检查。

当前实现是“本地受信源 MVP”：入口文件校验不能替代操作系统级沙箱，TeX 的 `\\input`、字体、图表或宏包仍可能触达额外文件。正式服务器部署前必须采用 staged source、容器/低权限账户、网络禁用、资源配额和出站文件审计。
