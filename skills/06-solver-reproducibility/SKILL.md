---
name: 06-solver-reproducibility
description: 将已登记模型实现为可复现的 Python/MATLAB/优化或仿真运行，记录配置、环境、种子、中间检查、结果文件和哈希；适用于生成论文数字与附录代码。
---

# 求解工程与可复现运行

本技能把“程序跑过一次”提升为别人能在干净环境重跑、对照和定位的 run_manifest。
资料包代码只提供迁移线索，不能直接信任或执行。

## 输入与输出

输入：model-contract、equation_registry、data-contract、代码/工具版本、计算预算。

输出：

- 相对路径入口脚本和配置；
- 环境锁定（Python/MATLAB/求解器/OS/包版本）；
- run-manifest/v2；
- 原始、处理中间量、结果表/图和 SHA-256；
- 命令、退出码、日志、随机种子和停止原因；
- 失败/超时/近似路线记录。

## 实现顺序

1. 从方程和变量表建立代码变量映射，禁止同名异义；
2. 将参数、单位、边界、目标、约束和随机源集中到配置；
3. 先写最小可运行 baseline 和小算例/极限案例；
4. 再实现 primary，保留中间量和约束余量；
5. 固定 seed（随机方法）并报告重复数、样本量和区间；
6. 在隔离/干净环境中运行，保存 stdout/stderr 和依赖版本；
7. 生成结果 artifact、manifest 和下一步验证请求。

## 结果一致性

- 论文、摘要、图表和附录从同一结果 artifact 取数字；
- 每个关键数值有单位、有效位、范围、分母和情景；
- 优化解同时输出决策变量、目标值、约束余量和可执行方案；
- 预测输出误差、区间和评估窗口；
- 机制/仿真输出状态、守恒/边界残差和重复统计。

## 工具选择

资料包含 MATLAB、Python、SPSS、LINGO、COMSOL 案例。选择工具时登记：

- 为什么该工具适合方程/数据/规模；
- 版本和许可证；
- 是否能在干净环境安装/运行；
- 失败时的可复现 fallback。

不执行资料盘中的安装器、宏、DLL、MEX 或未知脚本；需要借鉴时只提取算法思想并在
仓库内重写最小实现。

## 超时与失败策略

预先写时间盒和停止条件。无收敛、内存不足、求解器异常或结果违反硬约束时：

1. 保存失败日志和输入 revision；
2. 标 UNVERIFIED/BLOCKED；
3. 切换已登记 fallback 或缩小经证明的测试域；
4. 不把部分输出写成最终数字。

## 硬门

- 路径写死到个人机器：BLOCKED；
- 无 seed/环境/命令/退出码：UNVERIFIED；
- 结果文件未 hash 或被手工改写：BLOCKED；
- 只保存最终数字没有中间检查：UNVERIFIED；
- 程序与论文数字不一致：BLOCKED；
- 未记录整数性、约束或未来信息：BLOCKED。

运行：

~~~powershell
python -X utf8 skills/06-solver-reproducibility/scripts/validate_run_manifest.py run-manifest.json --strict
~~~

详细字段读取 references/artifact-contracts.md。
