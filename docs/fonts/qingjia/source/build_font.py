#!/usr/bin/env python3
"""Build QingJia Oracle Display from the bundled outline source.

Outputs:
  dist/QingJiaOracleDisplay-Regular.ttf
  dist/QingJiaOracleDisplay-Regular.woff2

No FontForge is required. Only fontTools (and Brotli for WOFF2) is used.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

try:
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont, newTable
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "缺少 fontTools。请先运行：python -m pip install -r requirements.txt"
    ) from exc

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "source" / "qingjia_oracle_glyphs.json.gz"
DEFAULT_OUTPUT = ROOT / "dist"


def glyph_name(codepoint: int) -> str:
    if codepoint == 0x20:
        return "space"
    if codepoint <= 0xFFFF:
        return f"uni{codepoint:04X}"
    return f"u{codepoint:05X}"


def make_glyph(contours: list[list[list[int]]]):
    pen = TTGlyphPen(None)
    for contour in contours:
        if len(contour) < 3:
            continue
        pen.moveTo(tuple(contour[0]))
        for point in contour[1:]:
            pen.lineTo(tuple(point))
        pen.closePath()
    return pen.glyph()


def make_notdef():
    pen = TTGlyphPen(None)
    pen.moveTo((50, -100))
    pen.lineTo((550, -100))
    pen.lineTo((550, 760))
    pen.lineTo((50, 760))
    pen.closePath()
    # Counter is opposite winding.
    pen.moveTo((470, -15))
    pen.lineTo((130, -15))
    pen.lineTo((130, 675))
    pen.lineTo((470, 675))
    pen.closePath()
    pen.moveTo((168, 80))
    pen.lineTo((433, 570))
    pen.lineTo((388, 600))
    pen.lineTo((123, 110))
    pen.closePath()
    return pen.glyph()


def build(output_dir: Path, make_woff2: bool = True) -> tuple[Path, Path | None]:
    if not DATA_FILE.exists():
        raise SystemExit(f"找不到轮廓源文件：{DATA_FILE}")

    with gzip.open(DATA_FILE, "rt", encoding="utf-8") as handle:
        data = json.load(handle)

    if data.get("format") != "QingJiaGlyphContours/1":
        raise SystemExit("轮廓源文件格式不受支持。")

    output_dir.mkdir(parents=True, exist_ok=True)
    units_per_em = int(data.get("units_per_em", 1000))
    metrics_data = data.get("metrics", {})
    ascender = int(metrics_data.get("ascender", 820))
    descender = int(metrics_data.get("descender", -200))
    line_gap = int(metrics_data.get("line_gap", 80))

    glyph_order = [".notdef"]
    glyphs = {".notdef": make_notdef()}
    horizontal_metrics = {".notdef": (600, 50)}
    cmap: dict[int, str] = {}

    for codepoint, advance, contours in data["glyphs"]:
        codepoint = int(codepoint)
        name = glyph_name(codepoint)
        if name in glyphs:
            continue
        glyph_order.append(name)
        glyphs[name] = make_glyph(contours)
        xs = [point[0] for contour in contours for point in contour]
        left_side_bearing = min(xs) if xs else 0
        horizontal_metrics[name] = (int(advance), int(left_side_bearing))
        cmap[codepoint] = name

    font_builder = FontBuilder(units_per_em, isTTF=True)
    font_builder.setupGlyphOrder(glyph_order)
    font_builder.setupCharacterMap(cmap)
    font_builder.setupGlyf(glyphs)
    font_builder.setupHorizontalMetrics(horizontal_metrics)
    font_builder.setupHorizontalHeader(
        ascent=ascender,
        descent=descender,
        lineGap=line_gap,
    )
    font_builder.setupNameTable(
        {
            "familyName": "QingJia Oracle Display",
            "styleName": "Regular",
            "uniqueFontIdentifier": "QingJia Oracle Display Regular 0.1.0",
            "fullName": "QingJia Oracle Display Regular",
            "psName": "QingJiaOracleDisplay-Regular",
            "version": "Version 0.1.0",
        }
    )
    font_builder.setupOS2(
        sTypoAscender=ascender,
        sTypoDescender=descender,
        sTypoLineGap=line_gap,
        usWinAscent=850,
        usWinDescent=220,
        usWeightClass=400,
        usWidthClass=5,
        fsSelection=0x0040,
        ulCodePageRange1=(1 << 0) | (1 << 18),  # Latin 1 + Simplified Chinese (GBK/936)
        panose={
            "bFamilyType": 2,
            "bSerifStyle": 11,
            "bWeight": 4,
            "bProportion": 3,
            "bContrast": 2,
            "bStrokeVariation": 8,
            "bArmStyle": 3,
            "bLetterForm": 2,
            "bMidline": 2,
            "bXHeight": 4,
        },
    )
    font_builder.setupPost(keepGlyphNames=True)
    font_builder.setupMaxp()

    font = font_builder.font
    name_table = font["name"]
    # Simplified Chinese localized names.
    name_table.setName("青甲骨刻体", 1, 3, 1, 0x0804)
    name_table.setName("常规", 2, 3, 1, 0x0804)
    name_table.setName("青甲骨刻体 常规", 4, 3, 1, 0x0804)
    name_table.setName("青甲骨刻体", 16, 3, 1, 0x0804)
    name_table.setName("常规", 17, 3, 1, 0x0804)

    copyright_text = (
        "Copyright (C) 1999 Arphic Technology Co., Ltd. "
        "Modified 2026 as QingJia Oracle Display; distributed under the ARPHIC PUBLIC LICENSE."
    )
    license_text = (
        "This modified font is distributed under the ARPHIC PUBLIC LICENSE. "
        "See licenses/ARPHIC_PUBLIC_LICENSE.txt in the source package. NO WARRANTY."
    )
    name_table.setName(copyright_text, 0, 3, 1, 0x0409)
    name_table.setName(license_text, 13, 3, 1, 0x0409)
    name_table.setName("QingJia Oracle Display", 16, 3, 1, 0x0409)
    name_table.setName("Regular", 17, 3, 1, 0x0409)

    # Basic Latin kerning. Chinese glyphs remain monospaced within the em square.
    feature_text = """
    feature kern {
        pos uni0041 uni0056 -36;
        pos uni0041 uni0057 -28;
        pos uni0041 uni0059 -34;
        pos uni0054 uni0061 -24;
        pos uni0054 uni0065 -24;
        pos uni0054 uni006F -24;
        pos uni0056 uni0061 -28;
        pos uni0057 uni0061 -22;
        pos uni0059 uni0061 -30;
        pos uni0051 uni004A -18;
    } kern;
    """
    addOpenTypeFeaturesFromString(font, feature_text)

    gasp = newTable("gasp")
    gasp.version = 1
    gasp.gaspRange = {65535: 0x000F}
    font["gasp"] = gasp

    ttf_path = output_dir / "QingJiaOracleDisplay-Regular.ttf"
    font.save(ttf_path)

    woff2_path: Path | None = None
    if make_woff2:
        try:
            web_font = TTFont(ttf_path)
            web_font.flavor = "woff2"
            woff2_path = output_dir / "QingJiaOracleDisplay-Regular.woff2"
            web_font.save(woff2_path)
        except Exception as exc:  # WOFF2 is optional when Brotli is unavailable.
            print(f"警告：未生成 WOFF2（{exc}）", file=sys.stderr)

    print(f"已生成：{ttf_path}")
    if woff2_path:
        print(f"已生成：{woff2_path}")
    print(f"字形数量：{len(glyph_order)}（含 .notdef）")
    return ttf_path, woff2_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建青甲骨刻体 TTF/WOFF2")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="输出目录，默认 ./dist",
    )
    parser.add_argument(
        "--ttf-only",
        action="store_true",
        help="仅生成 TTF，不生成 WOFF2",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build(args.output_dir, make_woff2=not args.ttf_only)
