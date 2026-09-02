# T-22 Skill v2 架构决策

## 目标

把资料包中分散的评阅信号、范文观察、算法代码经验、排版约定和外部运行审计
整理成可发现、可组合、可验证的技能层。系统同时提供：

- 高教社杯固定主流程：完整性优先，阶段之间有状态门；
- DIY 拼图流程：用户可以替换某一小问的方法，但不能绕过题面、证据、验证和发布门；
- 训练流程：把备赛、范文分析、算法练习和限时演练拆开；
- 机器可读注册表：前端、后端和其他 Agent 从同一 revision 发现技能。

## 为什么不继续保留旧技能

旧目录把阶段说明、工作流和脚本混在扁平 Markdown 中，存在三个问题：

1. 不能区分官方规则、模板习惯、范文观察和协调者推断；
2. 没有统一的输入/输出契约，算法命中容易被误当作选模结论；
3. 评审、复现、排版和发布被当作末尾步骤，无法在拼图中作为硬门。

本分支会删除仓库 skills 目录中的旧扁平文件和旧目录；系统目录
C:\Users\zyy20\.codex\skills 不在删除范围。

## 新目录

每个技能目录至少有 SKILL.md、agents/openai.yaml 和 skill-manifest.json；
需要重复执行的逻辑放在 scripts，需要按需读取的长规则放在共享 references。

    skills/
      registry.json
      README.md
      references/
      scripts/
      tests/
      00-charter-and-safety/
      01-scope-lock/
      ...
      12-evidence-reconstruction/
      workflows-cumcm-main/
      workflows-prep-and-drill/
      workflows-diy-puzzle/

注册表旁的 `source-provenance.json` 是机器可读来源台账，记录资料包快照、哈希、证据
类别、支持范围和限制。它与每个 manifest 的 `source_ids` 交叉校验，并参与
`skill_registry_revision`；因此资料解释或来源绑定变化时，旧装配不能静默复用。

## 设计原则

- 证据先于主张：每一条可写入论文的结果都必须能回到题面、数据、运行或复算。
- 简单模型优先：复杂方法只有在基线不足且有增益和验证时才升级。
- 角色可替换：同一技能可以由 Codex、Claude、Antigravity、Qoder 或本地脚本执行；
  文件契约和审查门不依赖供应商。
- 机器与人分工：机器检查结构、哈希、端口、编译和重复性；人确认假设、创新、
  规则适用性和最终发布。
- 失败显式化：STALE、BLOCKED、PENDING_RESOLUTION 不得伪装成完成。

## 运行时接入

后端只读加载 skills/registry.json，提供目录、搜索和单技能详情接口，并把
skill_registry_revision 附在 capability catalog 中。前端可以按阶段和工作流
筛选；实际执行仍要由任务事件和 artifact manifest 驱动，不把 UI 文字当事实。

## 接受标准

1. 所有新 SKILL.md 通过 skill-creator quick_validate；
2. registry 校验器能发现缺失 manifest、坏路径、重复 ID、旧引用和失效链接；
3. DIY、数据和运行 manifest 至少各有一个可运行的负例/正例测试；
4. API 能返回 registry revision、技能目录和搜索结果；
5. 旧技能调用方已迁移，仓库不再把旧路径当作当前入口；
6. 后端既有测试和前端语法检查的结果被记录，基线失败不被掩盖；
7. Git diff、提交和分支状态可回放。
