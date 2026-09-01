# 工作流拼图工作台

## 目标

工作流拼图是建模议事厅的“装配层”，把一篇数学建模论文拆成可以审查、替换和复跑的步骤。它不是自动选模器，也不把范文结论复制到新题；每一块只承诺一个可追踪的输入—输出接口，方法卡只提供候选假设。

工作台有两个入口：

1. **固定方案**：先选题型起点，再预览一条已经保留硬门的路线；点击“应用”才写入当前装配。
2. **DIY 拼图**：在固定骨架上逐块插入、移动、移除或替换方法卡。未选方法会显示为“待选”，不会伪装成已验证结论；类型契约不匹配会在拼图层阻断替换。

## 用户操作协议

### 固定方案

固定方案卡只负责生成结构，不替用户决定数学模型。每张卡包含：

- 适用的题型 archetype；
- 块顺序和硬门覆盖；
- 预览用的青龙拼图视觉索引；
- 应用后可继续 DIY 的提示。

预览与应用使用同一份 `block_ids` 快照；固定方案不会因为题型起点而
静默删块。若需要按题型收束路线，应另建一张明确命名的方案卡，或在
应用前由群主确认收束后的预览。

当前目录提供“标准国赛链”“数据驱动快线”“机制仿真线”。它们都保留 `problem-decomposition`、`baseline-model`、`validation`、`writing` 四个产品硬门；其余块是按题型增减的可组合扩展。

### DIY 拼图

每个工作流块对应一个交付步骤，而不是一个算法名称。常用步骤包括：题面拆解、数据审计、参数/情景契约、透明基线、机制模型、优化求解、情景仿真、题型验证、敏感性分析、独立质疑、论文写作和答辩准备。

点击拼图块后，右侧方法槽按兼容接口展示候选卡。方法卡至少应说明：

```text
适用条件 · 禁用条件 · 假设 · 输入 · 输出
验证方式 · 回退路线 · evidence_refs · compatible_block_kinds
```

`compatible_block_kinds` 是机器可检查的类型契约；旧目录没有该字段时，前端才退回 family 启发式匹配。点击“全部候选”可以看到不匹配卡，但不允许直接替换，以免把算法名误接到错误步骤。

## 结构门与数学门

工作台把“结构可审”和“数学已正确”严格分开：

- 前端本地检查：必选块是否存在、方法是否透明待选、草稿是否来自旧 revision；
- 后端权威检查：节点引用、端口类型、必需输入、DAG 无环、模型→验证→写作证据链和硬门；旧客户端提交的跨块方法保留为显式 `method_block_warnings`，前端拼图层不会提供这类不匹配替换；
- 数学结论检查：题面逐句核对、参数来源、量纲/守恒、独立复算、反例/敏感性和群主审批。

因此“结构可审”只表示可以进入审查，不表示数值结果、创新 claim 或论文已经通过比赛级验证。发送到群聊的事件仍带有 revision 和状态，不能绕过 Owner 门。

## 状态同步与草稿安全

前端优先使用宿主的 `qingjiaCapabilityBridge`，但桥接目录尚未返回时会先显示本地 fixture，保持编辑器可用；真实目录到达后在后台升级为 live。升级期间：

- 本地新增/移动/替换不会被空的旧投影清除；
- 本地装配会尝试恢复到宿主桥，随后以宿主的规范节点 ID 为准；
- 后台快照重新编号时，当前选中的块按块类型和出现次序重定位，不跳到第一块；
- revision 变化会显示 stale 提示，由用户选择恢复或重新应用，不静默覆盖。

无后端时，草稿只保存在浏览器本地 `qingjia.workflowPuzzle.v1`，提交提示会明确写出“本地演示模式，尚未写入群聊事实源”。

## 视觉资产

本版本使用 ImageGen 生成两张无文字、透明背景的系统资产：

- `assets/workflow/qinglong-puzzle-guide-v1.png`：小青龙抱住拼图块，用于空状态和工作台引导；
- `assets/workflow/qinglong-puzzle-atlas-v1.png`：六个语义切片（题面、数据、契约、求解、验证/质疑、写作/答辩），作为拼图块的视觉索引。

图像只表达步骤类别，不承载题面数字、模型参数或论文事实。CSS 通过 `background-position` 选取切片，避免把一张生成图误当作六个独立事实图标。

## 宿主接口

前端模块公开 `window.qingjiaPuzzleStudio`：

```text
boot()          初始化目录、草稿和事件监听
open()/close()  打开或关闭工作台
refreshCatalog  刷新能力目录
applyPreset()   应用当前固定方案
validate()      请求结构检查（无桥时使用透明本地检查）
getState()      返回脱敏的当前前端状态快照
```

宿主桥的最小读写边界为：

```text
getCatalog / loadCatalog / getAssembly / getRevision
setSelection / applyPreset / addBlock / insertBlock
replaceMethod / moveNode / removeNode / restoreAssembly
validate / send
```

模块不读取任意文件、不执行目录中的代码、不把知识库正文直接写入方法卡。后端静态服务器只允许根级 UI 白名单资源，`workflow-puzzle.js` 已加入白名单。

## 验收清单

### 静态与语法

```powershell
node --check workflow-puzzle.js
git diff --check
```

### 后端

为避免 Windows 默认临时目录权限问题，使用仓库内的临时目录运行：

```powershell
python -m pytest backend -q --basetemp .pytest-tmp
```

验收应覆盖能力目录字段、全部 workflow kind 的方法卡、多候选方法、静态资源白名单和 API 回归。

### 浏览器行为

至少验证以下路径：

1. 右侧“工作流拼图”打开全屏工作台；
2. 三张固定方案可预览，应用后进入 DIY；
3. DIY 能插入、移动、替换、移除块；
4. problem/data/contract/baseline/mechanism/optimization/simulation/validation/review/writing/defense 均能显示类型匹配的方法卡；
5. 未补齐硬门时发送按钮禁用，补齐后只提示“结构可审”；
6. fixture 与 live 两种目录切换不丢草稿；
7. 桌面与窄视口没有横向溢出，生成图加载失败时文字仍可读。

## 维护原则

- 新增块先写端口和验证门，再写视觉；
- 新增方法先写禁用条件和 fallback，再加入推荐列表；
- 每次目录 revision 变化都保留 stale 处理和迁移说明；
- 生产运行以版本化事件/工件为事实源，聊天只是投影；
- 任何“适用于所有赛题”的表述都必须改写为“候选接口覆盖”，并保留未知边界。
