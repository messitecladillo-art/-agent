# 青甲骨刻体 QingJia Oracle Display v0.1

一款为“青甲 Agent”主题定制的东方未来展示字体。字形以细长的楷意骨架为基础，经过单线化、菱形扩笔、方向微偏移与细小刻痕处理，形成“甲骨刻写 × 玉石科技”的视觉气质。

> 本包不包含预编译的 `.ttf/.otf/.woff2` 二进制字体；运行随附脚本后，会在本地生成可安装、可导入的 TTF 与 WOFF2 文件。

## 一键构建

### Windows

双击 `build_windows.bat`。脚本会安装所需的 Python 依赖并生成字体。

### macOS / Linux

在终端进入本文件夹后运行：

```bash
./build_macos_linux.sh
```

也可手动运行：

```bash
python3 -m pip install -r requirements.txt
python3 build_font.py
```

构建完成后可在 `dist/` 中看到：

- `QingJiaOracleDisplay-Regular.ttf`：适合系统安装、Figma、Sketch、Adobe 软件及 Office。
- `QingJiaOracleDisplay-Regular.woff2`：适合网页与前端项目。

只需 TTF 时：

```bash
python3 build_font.py --ttf-only
```

## 字符覆盖

- ASCII：U+0020–U+007E。
- GB2312 可解码字符：简体中文常用字、标点、全角字符、希腊字母、日文假名等核心集合。
- 青甲主题符号：U+E000–U+E009，共 10 个私用区图标。
- 具体数量及映射见 `CHARSET.txt`。

本版本面向品牌标题、产品模块标题、运营海报和重点数字，不是完整 Unicode CJK 字体。生僻字、繁体扩展字与部分少数民族文字可能缺失。

## 主题符号

| 码位 | 含义 | HTML 写法 |
|---|---|---|
| U+E000 | 品牌印记 | `&#xE000;` |
| U+E001 | 小青龙头像 | `&#xE001;` |
| U+E002 | 甲骨刻片 | `&#xE002;` |
| U+E003 | 云纹 | `&#xE003;` |
| U+E004 | 玉璧 | `&#xE004;` |
| U+E005 | 灵感闪光 | `&#xE005;` |
| U+E006 | 搜索 | `&#xE006;` |
| U+E007 | 发送 | `&#xE007;` |
| U+E008 | 知识书卷 | `&#xE008;` |
| U+E009 | Agent 协作 | `&#xE009;` |

在 Figma、Illustrator 等软件中，可通过“字符/字形”面板按 Unicode 码位插入。私用区符号只有在使用本字体时才能正确显示。

## 前端使用

构建字体后，将 `dist/` 复制进项目，并参考 `sample.css`：

```css
@font-face {
  font-family: "QingJia Oracle Display";
  src: url("./dist/QingJiaOracleDisplay-Regular.woff2") format("woff2");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}

.qingjia-title {
  font-family: "QingJia Oracle Display", "Noto Sans SC", sans-serif;
  letter-spacing: 0.06em;
  font-synthesis: none;
}
```

## 推荐用法

- 品牌主标题：32–72 px，字距 `0.04em–0.10em`。
- 页面模块标题：20–32 px，字距 `0.03em–0.07em`。
- 导航重点项：16–22 px；小于 16 px 时建议切换到常规黑体。
- 正文建议搭配系统无衬线中文字体，不建议整段长文全部使用本字体。
- 青绿或深墨色最能体现刻痕轮廓；浅色背景下效果最佳。

打开 `preview/preview_after_build.html` 可查看网页样张；该页面会从 `../dist/` 读取构建后的 WOFF2。

## 文件结构

```text
├─ build_font.py                 字体构建脚本
├─ build_windows.bat             Windows 一键构建
├─ build_macos_linux.sh          macOS/Linux 构建
├─ requirements.txt              Python 依赖
├─ source/
│  ├─ qingjia_oracle_glyphs.json.gz  压缩轮廓源
│  └─ metadata.json
├─ preview/
│  ├─ 青甲骨刻体_样张.png
│  ├─ 青甲骨刻体_核心字形.svg
│  └─ preview_after_build.html
├─ licenses/
│  └─ ARPHIC_PUBLIC_LICENSE_AND_COPYRIGHT.txt
├─ CHARSET.txt
├─ FONTLOG.md
├─ MODIFICATION_NOTICE.txt
└─ sample.css
```

## 技术说明与限制

- 轮廓为直线化多边形，未加入人工 TrueType hinting；高分屏、网页和设计软件中表现更佳。
- 字形采用展示性细线结构，极小字号或低分辨率打印可能显得偏细。
- v0.1 为单字重 Regular；后续可继续扩展 Medium、Bold、可变字重及完整简繁字符集。
- 构建依赖 Python 3.10+ 与 `fontTools`；生成 WOFF2 还需要 Brotli，已包含在 `fonttools[woff]` 依赖中。

## 许可与来源说明

本字体的中文及拉丁字形骨架经过算法处理，来源于 **AR PL KaitiM GB**。修改版及其构建源依照 **ARPHIC PUBLIC LICENSE** 分发，完整条款见 `licenses/ARPHIC_PUBLIC_LICENSE_AND_COPYRIGHT.txt`。

再分发生成的字体文件或本源包时，请保留许可证与 `MODIFICATION_NOTICE.txt`，并保持修改源可获得。使用字体制作界面、图片、视频、印刷品等成果，与再分发字体文件是不同场景；涉及正式商业授权与法务要求时，请自行进行合规确认。
