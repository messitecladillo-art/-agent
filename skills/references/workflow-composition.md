# 固定流程与 DIY 拼图协议

## 1. 标准端口类型

| 端口 | 说明 |
|---|---|
| problem_contract | 已锁定题面、规则、附件和任务动词 |
| question_map | 小问、依赖 DAG 和交付物 |
| data_contract | 字段、单位、质量、切分和来源 |
| mechanism_contract | 变量、方程、边界、初值和参数 |
| model_contract | 目标、约束、假设和可行域 |
| route_spec | baseline/primary/fallback 与方法理由 |
| run_manifest | 可重放命令、环境、种子和结果哈希 |
| validation_report | 检验、灵敏度、反例和独立复算 |
| paper_contract | 章节、公式、表图、引用和渲染产物 |
| release_pack | 最终文件、证据索引、审批和风险 |

## 2. 固定链

charter → scope-lock → question-decomposition → data/evidence →
model-routing → mathematical-derivation → solver-reproducibility →
validation/adversarial-review → paper/typesetting → defense/release。

每一箭头都是状态门，不是简单的 UI 连线。允许在同一阶段回退修复，但不能
跳过题面锁定、数据契约、基线、验证或发布审查。

## 3. DIY 组合规则

一个 block 至少声明：

    id, kind, inputs, outputs, required_inputs, method_id
    owner, source_refs, assumptions, prohibitions
    validation_kinds, status, input_revision

校验器必须检查：

1. 节点 ID、端口和方法 ID 唯一；
2. 同名端口类型兼容；
3. 边不形成环；
4. 必需块 problem-decomposition、baseline-model、validation、writing 存在；
5. 每个小问有输出、验证和写作映射；
6. 所有随机块有种子，所有外部输入有哈希；
7. 缺失证据只能保存 DRAFT，不能 SUBMIT_REVIEW；
8. 有未来信息、未知代码执行或越权写集时直接 BLOCKED。

## 4. 适配与创新

固定链解决完整性；DIY 解决题型差异。新增方法先放在候选卡，填写适用域、
禁用条件、假设、输入输出和验证，再加入拼图。创新不是增加算法数量，而是
对本题定义新量、建立新机制、改进约束/求解或提出可验证的新方案。
