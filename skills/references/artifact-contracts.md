# 数学建模产物契约

以下 JSON 片段是字段约定，不是要求每次都生成完全相同的文件名。字段缺失时
应阻断下游，除非明确标记为草稿。

## 1. ProblemContract

    schema_version: problem-contract/v2
    problem_id
    contest_profile:
      contest, edition, group, region, stage, problem_id
      rule_refs[], format_refs[]
    statement_refs[]
    attachment_refs[]
    task_verbs[]
    constraints[]
    online_information_policy
    deliverables[]
    input_revision
    status

每个 task_verb 要包含 question_id、原句引用、目标量、单位、输出形式和来源。

## 2. QuestionMap

    schema_version: question-map/v2
    problem_id
    questions:
      - id
        statement_refs[]
        objective
        inputs[]
        outputs[]
        dependencies[]
        baseline
        primary_route
        fallback_route
        validation_requirements[]
        owner
        status
    edges[]
    coverage[]
    input_revision

edges 必须构成 DAG；每个小问都要有输出和覆盖状态。

## 3. DataContract

    schema_version: data-contract/v2
    dataset_id
    input_revision
    raw_assets:
      - path, sha256, immutable, source_ref
    fields:
      - name, role, dtype, unit, time_grain, spatial_grain
        source_ref, missing_policy, outlier_policy, transform
    splits:
      strategy, train_refs[], validation_refs[], test_refs[]
      group_key, time_cutoff, leakage_checks[]
    quality:
      row_count_reconciliation, duplicate_check, range_checks[]
      missing_report, anomaly_report
    status

原始资产永不覆盖；清洗结果另存并保留映射。

## 4. ModelRoute

    schema_version: model-route/v2
    question_id
    structural_cues[]
    baseline:
      method_id, rationale, assumptions[], metrics[]
    primary:
      method_id, rationale, assumptions[], equations[], constraints[]
      solver_config, expected_outputs[]
    fallbacks[]
    prohibited_shortcuts[]
    validation_plan[]
    evidence_refs[]
    status

至少有一个透明基线和一个可触发的 fallback；算法堆叠不等于路线。

## 5. RunManifest

    schema_version: run-manifest/v2
    run_id, input_revision, code_revision, route_revision
    environment:
      interpreter, packages[], os, solver_versions[]
    command, cwd
    seed_policy:
      deterministic, seeds[], random_sources[]
    checkpoints[]
    artifacts:
      - path, sha256, media_type, produced_by
    exit_code, stdout_sha256, stderr_sha256
    status

## 6. ValidationReport

    schema_version: validation-report/v2
    target_id, input_revision, run_id
    checks:
      - id, kind, method, threshold, observed, unit, status, evidence_refs[]
    sensitivity[]
    counterexamples[]
    independent_reproduction
    blockers[]
    status

## 7. PaperContract 与 ReleasePack

PaperContract 至少包含 profile、sections、notation、equations、tables、figures、
references、page_budget、render_artifacts 和 coverage_refs。ReleasePack 至少包含
题面/附件索引、最终 PDF 哈希、代码/环境 manifest、验证报告、匿名/版权检查、
未决项和 Owner 审批。
