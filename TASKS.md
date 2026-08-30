# 任务看板

> 任务的唯一事实来源。开工前 `git pull` 读本文件；认领/完成/评审后**立即更新并提交**。
> 状态流转：待认领 → 进行中 → 待审 → 已完成。任务编号格式 `T-<序号>`。

## 进行中

| ID | 任务 | 负责人 | 分支 | 备注 |
|---|---|---|---|---|
| T-01 | 创建 GitHub 私有仓库并绑定远端 | 人 | — | 完成后运行 `git remote add origin <url> && git push -u origin main` |

## 待认领

| ID | 任务 | 优先级 | 验收标准 |
|---|---|---|---|
| T-02 | 配置本地 Python 环境与 `.env` | 高 | `pip install anthropic` 成功，`.env` 含有效 KEY |
| T-03 | 跑通独立评审脚本 | 高 | `python scripts/agents/review.py README.md` 生成评审报告到 `notes/reviews/` |
| T-04 | 在 Codex 中绑定 GitHub 仓库 | 高 | 能从 Codex 对该仓库派发云端任务 |
| T-05 | 用 Antigravity 打开本目录 | 中 | 工作区正常，能读取 AGENTS.md |

## 待审

（暂无）

## 已完成

| ID | 任务 | 完成日期 |
|---|---|---|
| T-00 | 初始化项目骨架与团队守则 | 2026-08-31 |

---

## 任务模板（复制使用）

```
| T-xx | <一句话任务> | 高/中/低 | <可检查的验收标准> |
```
