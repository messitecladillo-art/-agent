# 数学建模

面向数学建模竞赛/科研的多代理协作工作区。四类 AI 成员与人在同一个 git 仓库上协作：
`TASKS.md` 是任务唯一事实来源，`AGENTS.md` 是协作守则，仓库文件是唯一的信息同步黑板。

## 成员与分工（详见 AGENTS.md）

| 成员 | 角色 |
|---|---|
| Qoder | 协调中枢：拆解任务、审查合并、问题分析、论文写作 |
| Codex | 编码工人：算法实现、求解代码、数据处理（走 GitHub PR 流程） |
| Antigravity | 验证与展示：可视化图表、演示界面、浏览器端验证 |
| Claude API 脚本 | 批量工/独立评审员/定时分析员（见 scripts/agents/） |

## 接入各工具

1. 在 GitHub 上创建**私有仓库**并关联：
   ```
   git remote add origin <你的仓库地址>
   git push -u origin main
   ```
2. **Codex**：在 Codex 中绑定该 GitHub 仓库，之后用云端任务派活，产出以 PR 形式回来
3. **Antigravity**：直接用本目录作为工作区打开
4. **Qoder**：在本目录打开新会话即可，它会自动读取 AGENTS.md

## 目录结构

```
├─ AGENTS.md        # 团队守则（所有 AI 成员必读）
├─ TASKS.md         # 任务看板（唯一事实来源）
├─ notes/           # 共享笔记与结论（含 reviews/ 评审报告）
├─ data/            # raw/ 原始数据（不进仓库），processed/ 处理后数据
├─ models/          # 模型描述与求解代码（Codex 主导）
├─ experiments/     # 实验日志与结果（log.md 只追加）
├─ paper/           # 论文与图表（Qoder 主导）
├─ viz/             # 可视化/演示（Antigravity 主导）
└─ scripts/agents/  # Claude API 脚本化代理
```

## 配置独立评审脚本

```
pip install anthropic
cp .env.example .env    # 填入 ANTHROPIC_API_KEY
python scripts/agents/review.py paper/draft.md        # 评审单个文件
python scripts/agents/review.py --diff HEAD~1         # 评审一次改动的 diff
```

## 日常节奏

开工先 `git pull` 读 TASKS.md → 认领任务 → 在 `task/<ID>-<描述>` 分支干活 →
结果写进 notes/ 或 experiments/log.md → 任务移到"待审" → 协调者审查合并。
