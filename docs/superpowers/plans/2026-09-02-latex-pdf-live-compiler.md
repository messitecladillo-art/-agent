# LaTeX/PDF 实时编译器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为建模议事厅增加一个安全、可观察、可复现的 LaTeX → PDF 编译能力，并通过 WebSocket/轮询把编译进度和 PDF 审计状态实时呈现给群主。

**Architecture:** 新增独立的 `backend/latex_compiler.py` 作为编译边界：只接受仓库内允许的 `.tex` 入口，使用固定 argv、无 shell 的子进程和运行时 build 目录，输出编译日志、PDF 元数据和 SHA-256。`backend/app.py` 提供能力探测、创建任务、任务状态和 PDF 白名单下载接口；任务状态通过现有事件总线广播。前端在控制面增加轻量“论文编译”卡片，不把编译成功当作数学或论文验收通过。

**Tech Stack:** Python 3.9 stdlib、FastAPI/Pydantic、Tectonic/XeLaTeX/latexmk（按探测结果选择）、Poppler `pdfinfo`、原生 JavaScript/CSS、现有 WebSocket 事件源。

**Spec:** 用户请求“配置加入 latex 与 pdf 实时编译器”；行为边界以 `backend/README.md`、`docs/api-contract.md`、`skills/latex-compile` 和 `skills/pdf` 的要求为准。

## Global Constraints

- 编译入口只能解析仓库内 `paper/`、`models/`、`artifacts/` 下的 `.tex` 文件；拒绝绝对路径、`..`、符号链接和控制文件。
- 编译命令使用固定参数向量，`shell=False`，超时和输出长度有上限；不执行题面/资料目录中的任意脚本。
- 输出写入 `runtime/latex/`，不进入 Git，不覆盖源码；PDF 仅通过白名单 job ID 下载。
- 所有状态必须区分 `UNAVAILABLE`、`QUEUED`、`RUNNING`、`SUCCEEDED`、`FAILED`、`TIMED_OUT`；编译成功不等于数学验证或 Owner 审批通过。
- 真实编译器不存在时返回诚实的 `UNAVAILABLE`，不伪造 PDF；不自动安装 TeX/Poppler。
- 新增功能不改写现有任务、知识库、拼图或群聊状态机；只通过独立路由和可选前端卡片接入。

---

### Task 1: 编译边界与运行时契约

**Files:**
- Create: `backend/latex_compiler.py`
- Create: `backend/test_latex_compiler.py`
- Modify: `backend/requirements.txt` only if a runtime dependency is strictly required (prefer none)

**Interfaces:**
- `CompilerConfig(root: Path, build_root: Path, timeout_seconds: int = 120, max_log_bytes: int = 200_000)`
- `detect_toolchain() -> ToolchainReport`
- `validate_entrypoint(raw: str) -> Path` (raises `CompileInputError`)
- `compile_tex(entrypoint: str, *, compiler: str = "auto", engine: str = "auto", clean: bool = True) -> CompileResult`
- `CompileResult` is JSON-safe and includes `job_id`, `status`, `entrypoint`, `compiler`, `engine`, `started_at`, `finished_at`, `duration_ms`, `log_tail`, `pdf_path` (relative), `pdf_sha256`, `pdf_pages`, `pdf_bytes`, `error_code`.

- [x] **Step 1: Write failing tests** for traversal rejection, non-tex rejection, missing toolchain, fixed-argv/no-shell invocation, timeout status, successful PDF metadata parsing, and bounded log output.
- [x] **Step 2: Run `python -m pytest backend/test_latex_compiler.py -q` and confirm RED** because the module and interfaces do not yet exist.
- [x] **Step 3: Implement the minimal safe compiler service** with a deterministic job directory, `subprocess.run(..., shell=False, timeout=...)`, compiler detection (`tectonic`, `latexmk`, `xelatex`), `pdfinfo` parsing when available, and SHA-256 hashing.
- [x] **Step 4: Run the focused tests and then `python -m pytest backend -q --basetemp .pytest-tmp-t20`**; 13 focused and 151 full tests green.
- [x] **Step 5: Commit** with the T-20 implementation commit (coordinator merge gate).

### Task 2: FastAPI API 与实时事件

**Files:**
- Modify: `backend/app.py` near existing route models and WebSocket/event store
- Modify: `backend/test_api.py` or Create: `backend/test_latex_api.py`
- Modify: `backend/README.md` with exact endpoints and unavailable/production limits

**Interfaces:**
- `GET /api/projects/{project_id}/latex/toolchain`
- `POST /api/projects/{project_id}/latex/compile` body `{entrypoint, compiler, engine, clean, base_revision, idempotency_key}`; returns `202`-style JSON with `job_id` and `status`.
- `GET /api/projects/{project_id}/latex/jobs/{job_id}` returns the same bounded status object.
- `GET /api/projects/{project_id}/latex/jobs/{job_id}/pdf` serves only a successful job's PDF from `runtime/latex`.
- WebSocket broadcasts `LATEX_COMPILE_QUEUED`, `LATEX_COMPILE_STARTED`, `LATEX_COMPILE_FINISHED`/`LATEX_COMPILE_FAILED` with job ID and revision.

- [x] **Step 1: Write failing API tests** for toolchain response, project/path rejection, idempotency replay, queued job status, successful/failed status shape, PDF download boundary, and event emission.
- [x] **Step 2: Run the focused API tests and confirm RED.**
- [x] **Step 3: Implement request models, bounded in-memory job registry, background task runner, event broadcast, CAS/idempotency handling, and safe PDF response.**
- [x] **Step 4: Run API tests plus the full backend suite; verify no existing route changes.**
- [x] **Step 5: Commit** with the T-20 API integration included in the coordinator merge commit.

### Task 3: 前端论文编译卡片

**Files:**
- Modify: `index.html` in the existing tasks/control panel only
- Modify: `app.js` for API calls, WebSocket event projection, status/error rendering
- Modify: `styles.css` for compact card states and responsive layout
- Modify: `backend/test_api.py` only for endpoint contract if needed; no test fixtures in UI files

**Interfaces:**
- `loadLatexToolchain()` reads the toolchain endpoint.
- `startLatexCompile()` sends a fixed payload for `paper/main.tex` by default and requires an explicit user click.
- `renderLatexCompileStatus(status)` renders status, compiler, elapsed time, PDF pages/size/hash prefix and a download link only on `SUCCEEDED`.

- [x] **Step 1: Add a DOM smoke assertion or browser fixture expectation for the new card's disabled/unavailable state.**
- [x] **Step 2: Run the browser smoke check and confirm the new selector is absent/fails before markup is added.**
- [x] **Step 3: Add the compact UI and event handler; keep simulated mode explicitly unavailable and do not auto-run compilation on page load.**
- [x] **Step 4: Run `node --check app.js`, `node --check workflow-puzzle.js`, browser desktop/mobile smoke, and verify no console errors.**
- [x] **Step 5: Commit** with the T-20 frontend changes included in the coordinator merge commit.

### Task 4: PDF/LaTeX verification, docs, review, release

**Files:**
- Create: `docs/latex-pdf-live-compiler.md`
- Modify: `README.md` and `TASKS.md`
- Create: `notes/reviews/T-20-latex-pdf-live-compiler.md`
- Append: `experiments/log.md`

- [x] **Step 1: Run the actual compiler discovery and, if available, compile a temporary copy into `runtime/latex` without modifying source.**
- [x] **Step 2: Inspect the generated PDF with `pdfinfo`; record the available toolchain rather than inventing success.**
- [x] **Step 3: Have an independent read-only Critic/Auditor review changed paths, security boundaries, API/event contracts, UI fallback, and PDF evidence.**
- [x] **Step 4: Run full acceptance: focused tests, `python -m pytest backend -q`, compileall, Node checks, `git diff --check`, secret scan, and browser smoke.**
- [x] **Step 5: Mark T-20 complete after P0/P1 findings closed; commit and push through the coordinator’s normal merge gate.**
