# 青甲骨刻体（QingJia Oracle Display）接入记录

本目录记录本项目使用的“青甲骨刻体 / QingJia Oracle Display v0.1.0”展示字体。

## 用途边界

- 用于品牌名、建模首屏标题、甲骨文识别锚点和短标签。
- 正文、证据链、表格和小字号元数据继续使用系统无衬线字体。
- 字体只有 Regular / 400 一个字重，覆盖 ASCII、GB2312 核心字符和 10 个青甲主题私用区图标（U+E000–U+E009）。

## 来源与构建

- 用户提供源包：QingJiaOracleDisplay_SourcePack_v0.1.zip
- 源包 SHA-256：117A6D312B1D75967B5A0CB5A83322224FBD896752F48CBAD0484820CFE41E1A
- 构建脚本：source/build_font.py
- 构建环境：Python 3.13.9、fontTools 4.60.1、brotlicffi 1.1.0
- 构建命令：python source/build_font.py --output-dir assets/fonts/qingjia
- 字形映射：7562（另含 .notdef）

## 文件与校验

| 文件 | SHA-256 |
| --- | --- |
| assets/fonts/qingjia/QingJiaOracleDisplay-Regular.woff2 | 0A8615B322CBA592B590BA26F4C1E75883E4025D5C2634A04DBB0F86C4F42957 |
| assets/fonts/qingjia/QingJiaOracleDisplay-Regular.ttf | E511C3C7D7A76E73248C50AB9C4922F8367AC571D88D0E00BAD717008CD90001 |
| docs/fonts/qingjia/source/qingjia_oracle_glyphs.json.gz | ACFDA1280E5DC2DA049FF976095C3E8B16262A73CD3494F5194765A4586A2AA4 |

许可证、修改声明和源数据随项目保留：

- assets/fonts/qingjia/ARPHIC_PUBLIC_LICENSE_AND_COPYRIGHT.txt
- assets/fonts/qingjia/MODIFICATION_NOTICE.txt
- docs/fonts/qingjia/source/

字体源自 AR PL KaitiM GB 的算法化修改版，按 ARPHIC PUBLIC LICENSE 分发。若未来对外再分发字体文件，请同时保留许可证、修改声明和可获得的修改源。
