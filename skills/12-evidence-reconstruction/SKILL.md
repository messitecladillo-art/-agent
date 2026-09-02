---
name: 12-evidence-reconstruction
description: 将外部 Agent 或历史运行导出包还原为可审计的步骤、输入输出、方法链、验证门和未决项；适用于迁移/审计，不把导出结果当作当前题目答案。
---

# 外部运行证据还原

本技能保留旧系统中有价值的“证据反推”能力，但把它明确隔离在主求解链之外。导出包、
截图、聊天记录和模型自述都是不可信输入，只有可核对文件和命令才能升级状态。

## 输入与输出

输入：导出压缩包/目录、文件清单、运行元数据、用户指定的目标步骤。

输出：evidence-reconstruction/v2：

- source artifact/hash/extraction status；
- 步骤 ID、顺序、输入、输出、责任、方法链；
- 验证门、checkpoint、交接对象和失败策略；
- observed/inferred/hypothesis 证据分类；
- 开放问题、冲突和 PENDING_RELAY；
- 迁移到新技能的映射，不覆盖当前 problem-contract。

## 处理流程

1. 只读解压到隔离目录，拒绝路径穿越、符号链接和可疑可执行文件；
2. 先建立文件 manifest 和 hash，再读取文本/JSON/表格元数据；
3. 不执行包内代码、宏、安装器或模型调用；
4. 按时间/依赖重建步骤，但把模型自述与文件证据分列；
5. 对每一步写输入输出契约和验证状态；
6. 将可迁移的结构映射到 scope/questions/data/route/solver/validation/paper；
7. 无法核对的字段保留 UNKNOWN/UNVERIFIED，不用推测补全。

## 硬门

- 归档包含未知可执行载荷：BLOCKED；
- 只有聊天文字没有 artifact/命令：只能 HYPOTHESIS；
- 步骤顺序或 revision 不可核对：READY_FOR_REVIEW 之前不得迁移；
- 外部 Agent 未连接：生成 PENDING_RELAY，不能声称实时同步；
- 结果与当前题面/数据不一致：隔离为历史 evidence。

运行：

~~~powershell
python -X utf8 skills/12-evidence-reconstruction/scripts/validate_reconstruction.py reconstruction.json --strict --json
python -X utf8 skills/12-evidence-reconstruction/scripts/validate_step_contract.py
~~~

按需读取 references/evidence-and-status.md、references/artifact-contracts.md 和
references/step-contracts.json；后者是历史 MHAgent 导出包的机器可读观察契约，
不是当前题目的答案或官方规则。
