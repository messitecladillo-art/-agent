# Skill v2 回归夹具

从仓库根目录运行：

```powershell
python -X utf8 skills/tests/run_regression.py
```

脚本会依次检查：

- `registry.json`、所有 manifest、frontmatter、引用资源和旧入口消失；
- 每个注册 Skill 的 Codex `skill-creator` quick validator；
- 固定/DYI 拼图、数据契约、运行 manifest、外部证据重建的正例；
- 拼图负例确实被拒绝（预期退出码为 1）；
- 论文公式/契约的正反向夹具；
- Node.js 前端语法和 backend pytest（可用 `--skip-backend` 降级）。

这个目录的 JSON 是最小结构夹具，不代表真实赛题答案。负例通过“被拒绝”来证明
硬门仍然有效；不要把所有命令都要求返回 0。
