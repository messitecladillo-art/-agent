# 校赛 B 题论文交付

主稿为 [`b_problem_solution.tex`](b_problem_solution.tex)，编译产物为 [`b_problem_solution.pdf`](b_problem_solution.pdf)。本稿是基于用户提供题面和附件的“校赛内部复核版”，不是已经按主办方官方模板排版的最终投稿件；官方模板、匿名要求和页数尚未随输入提供。

## 复算与编译

```powershell
python -X utf8 models/solve_b_problem.py --input "<附件路径>\校赛B题附件.csv" --output runtime/solo-test/b_solution --seed 42
xelatex --enable-installer=f -interaction=nonstopmode -halt-on-error -file-line-error -output-directory runtime/solo-test/paper_build2 paper/b_problem_solution.tex
xelatex --enable-installer=f -interaction=nonstopmode -halt-on-error -file-line-error -output-directory runtime/solo-test/paper_build2 paper/b_problem_solution.tex
```

`paper/evidence/` 只保存聚合证据，不保存客户编码；求解器还会在本地运行目录生成 `group_rates.csv` 与 `scenario_segments.csv`，它们不纳入论文证据登记。输入文件哈希、依赖版本、运行命令和边界在 [`evidence/provenance.json`](evidence/provenance.json) 中。结构审计报告应由以下命令重新生成：

```powershell
python -X utf8 skills/08-paper-and-typesetting/scripts/audit_latex_math.py paper/b_problem_solution.tex --release --json
python -X utf8 skills/08-paper-and-typesetting/scripts/audit_paper_contract.py paper/b_problem_contract.json --strict --json
```

当前审计结果：LaTeX 结构 `PASS`、论文契约 `PASS`、XeLaTeX 双遍编译成功、PDF 12 页 A4，全页 PNG 视觉检查通过。Q4 的扰动参数和收益下界保持 `HYPOTHESIS` 边界，不能改写为已估计的竞争价格弹性。
