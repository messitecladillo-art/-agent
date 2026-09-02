# 前向验收夹具

这些夹具只测试 Skill 的结构性门，不代表任何数学题的正确答案。

```powershell
python ..\scripts\audit_latex_math.py good.tex --release
python ..\scripts\audit_latex_math.py bad.tex --release  # 应失败
python ..\scripts\audit_paper_contract.py good_contract.json --strict  # 应通过
python ..\scripts\audit_paper_contract.py bad_contract.json --strict   # 应失败
```

若契约注册表拆成多个文件，只对 `audit_paper_contract.py` 重复传 `--registry <path>`；
LaTeX 检查器不读取注册表。严格模式会拒绝与根契约不同的 `input_revision`。

测试覆盖：重复/断裂引用、缺少图表元数据、手写公式编号、未完成占位符、未声明变量、
量纲不一致、未知小问、未验证 claim、未知证据引用、注册表版本漂移和缺少 provenance。完整的 E01–E18 反例矩阵见
`references/registries-and-evidence.md` 所描述的门禁，实际论文仍需干净编译、视觉 QA
和独立数学审查。
