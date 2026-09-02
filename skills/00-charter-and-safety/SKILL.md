---
name: 00-charter-and-safety
description: 为数学建模任务建立证据、权限、版权、状态和发布边界；在任何解题、检索、写作或外部 Agent 协作开始前使用，避免把候选方法或资料命中冒充已验证事实。
---

# 建模工程章程与安全边界

这是所有其他技能的共同入口。它不替题目选模型，也不授权执行未知代码；它把一次建模
任务变成可回放的工程运行。

## 何时使用

- 新建一题、切换赛事/届次/组别或切换题号；
- 挂载资料库、外部 Agent、代码或论文；
- 任何结果准备进入论文、答辩或提交包；
- 旧结果要迁移到新 revision，或发现来源冲突。

## 输入与输出

输入必须列出：用户目标、题面/附件来源、赛事 profile、当前 Git commit 或 manifest、
可用工具和允许写入目录。

输出至少包括：

1. run charter：目标、非目标、角色、能力、数据分类、时间盒和停止条件；
2. source ledger：每个事实/建议的 source_ref、抽取状态和 claim_class；
3. artifact map：输入、输出、命令、哈希和 owner；
4. gate plan：下游技能、硬门、复核人和回退路线；
5. open-questions：缺失资料、冲突规则和需要 Owner 决策的项。

## 强制步骤

### 1. 锁定 revision

优先使用 Git commit/tree hash；非 Git 工程使用排序后的文件清单 SHA-256。把
input_revision、code_revision、capability_revision 和 control_revision 分开。任何
输入改变都让依赖它的 VERIFIED 产物回退为 STALE。

### 2. 分类主张

对每条记录写 OBSERVED、DERIVED、INFERRED、HYPOTHESIS、CANDIDATE、OFFICIAL_PENDING
之一。不要因为一个文件名、论文奖项或方法目录命中就升级到 OBSERVED。

### 3. 最小权限

默认只读题面、声明的附件、仓库 allowlist 和指定资料片段；只写分配的 artifact roots。
资料盘中的宏、安装器、DLL、MEX、脚本、未知压缩包和网络链接一律不执行。外部 Agent
未连接时输出 PENDING_RELAY，不声称已经同步。

### 4. 建立状态机

产物按 PROPOSED → PRODUCED → STRUCTURE_CHECKED → READY_FOR_REVIEW → VERIFIED →
ACCEPTED → RELEASED 推进。出现硬错误进入 BLOCKED；作者不能自己关闭 P0/P1。

### 5. 定义停止条件

为每个阶段写清“何时切换 fallback、何时请求 Owner、何时停止计算”。超时、无收敛、
来源冲突和预算耗尽都要记录，不得静默重试或伪造结果。

## 单 Agent 模式

若用户指定单 Agent，仍按 Scope、Producer、Critic、Challenger、Auditor 顺序串行执行；
每个角色写独立检查记录，不能用同一段推理给自己盖章。只有 Owner 能批准外部发布。

## 按需读取

- 证据等级、状态和主张字段：读取 references/evidence-and-status.md；
- 产物 schema：读取 references/artifact-contracts.md；
- 拼图端口和固定/DYI 规则：读取 references/workflow-composition.md；
- 资料来源和抽取限制：读取 notes/skill-rebuild-material-ledger.md。

## 失败处理

缺 revision、题面、官方 profile、数据来源或写入边界时，输出 BLOCKED 清单和最小补充
请求；不得用历史范文、默认参数或搜索摘要填空。若资料抽取乱码，保留 LOW confidence
并把人工视觉核验列为下一步。
