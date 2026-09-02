# 证据、主张与状态协议

## 1. 主张等级

每个进入聊天、论文、代码注释或发布包的句子都要标注 claim_class：

| claim_class | 可以说什么 | 必须有什么 |
|---|---|---|
| observed | 在文件、运行日志或接口中直接观察到的内容 | source_ref、抽取时间、原文/字段定位 |
| reproduced | 在当前 revision 按命令重新得到的结果 | run_manifest、命令、退出码、结果哈希 |
| independently_reproduced | 非原作者路径的独立复算 | 独立环境/实现、比较容差、中间量 |
| official_rule | 当前赛事官方要求 | 届次、组别、赛区/阶段、官方文件哈希 |
| official_review_signal | 官方评阅关注点 | 官方评阅文件哈希和定位 |
| exemplar_observation | 范文中观察到的做法 | 论文标识、页码/段落、不得外推因果 |
| code_observation | 已静态审计或隔离复现的代码行为 | 依赖、版本、输入、输出和运行日志 |
| curated_inference | 从多份来源归纳的建议 | 组成来源、适用范围、待验证标记 |
| hypothesis | 尚未证实的路线或解释 | 证伪问题、验证计划、不能写成结论 |

## 2. 生命周期

状态只能按以下方向推进：

DISCOVERED → EXTRACTED → CONTRACTED → RUNNABLE → VERIFIED →
INDEPENDENTLY_REPRODUCED → RELEASE_CANDIDATE → RELEASED

任一输入 revision、题面、规则、代码、数据或关键参数改变时，受影响产物
回退为 STALE；硬门失败时为 BLOCKED。PENDING_RESOLUTION 用于资料缺失、
规则未核验或外部 Agent 尚未回传，不能当作通过。

## 3. 最小证据索引

每条 claim 至少包含：

    claim_id
    text
    claim_class
    status
    source_refs[]
    input_revision
    code_revision
    produced_by
    verification[]
    limitations[]

source_ref 应是仓库相对路径加锚点、kbdoc 标识、运行 manifest 标识或官方
source_id；禁止只写“资料包”“网上资料”“模型显示”。

## 4. 冲突处理

1. 当届 official_rule 优先于旧模板、范文和经验。
2. 题面/附件事实优先于模型卡的通用假设。
3. 独立复算若与作者结果冲突，保留两份结果，标记 CONFLICTED，禁止平均或
   静默覆盖。
4. 乱码、缺页、哈希不匹配、未来信息、无法复现都要写入 unresolved。
5. 只有 Owner 在看到证据后才能将 BLOCKED/PENDING_RESOLUTION 改为 ACCEPTED。

## 5. 交接消息

跨 Agent 或模块传递时使用固定字段：

    protocol: gaojiao-agent-handoff/v2
    packet_id: UUID
    sender, receiver
    issued_at, expires_at
    base_revision, target_revision
    classification
    capabilities_used[]
    claims[]
    evidence_refs[]
    commands[]
    unresolved[]
    risks[]
    next_action

聊天消息只是通知；文件、事件日志、manifest 和 Git tree 才是事实源。
