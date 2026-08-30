"""独立评审员：调用 Claude API 评审文件或 git diff，报告落盘到 notes/reviews/。

用法：
    python scripts/agents/review.py <文件路径>      # 评审单个文件
    python scripts/agents/review.py --diff HEAD~1   # 评审一次改动的 diff

环境要求：
    pip install anthropic
    .env 中配置 ANTHROPIC_API_KEY（模型可用 REVIEW_MODEL 覆盖）
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL = os.getenv("REVIEW_MODEL", "claude-sonnet-4-5")

SYSTEM_PROMPT = (
    "你是数学建模竞赛的独立评审员（评委视角）。审查给定内容并输出问题清单，"
    "每个问题必须包含：1) 严重程度（阻塞/重要/轻微）2) 位置 3) 问题描述 4) 修改建议。"
    "重点检查：模型假设是否合理、推导与代码是否正确、结果与结论是否一致、"
    "是否缺少验证或灵敏度分析、写作逻辑是否清晰。"
    "用中文输出，markdown 格式；若无问题请明确说明。"
)


def load_env_file() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def read_input(args: argparse.Namespace) -> str:
    if args.diff:
        result = subprocess.run(
            ["git", "diff", args.diff],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            sys.exit(f"git diff 失败：{result.stderr.strip()}")
        if not result.stdout.strip():
            sys.exit(f"git diff {args.diff} 没有内容")
        return f"以下是 git diff（{args.diff}）：\n\n{result.stdout}"

    path = Path(args.path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.is_file():
        sys.exit(f"文件不存在：{path}")
    return f"以下是文件 {path.name} 的内容：\n\n{path.read_text(encoding='utf-8')}"


def review(content: str) -> str:
    try:
        import anthropic
    except ImportError:
        sys.exit("请先安装依赖：pip install anthropic")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def main() -> None:
    parser = argparse.ArgumentParser(description="独立评审脚本（Claude API）")
    parser.add_argument("path", nargs="?", help="要评审的文件路径（相对仓库根或绝对路径）")
    parser.add_argument("--diff", help="评审 git diff，如 HEAD~1 或 main...task/T-03-x")
    args = parser.parse_args()

    if bool(args.path) == bool(args.diff):
        sys.exit("请二选一：指定文件路径，或使用 --diff")

    load_env_file()
    report = review(read_input(args))

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    target = REPO_ROOT / "notes" / "reviews" / f"{stamp}-review.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    subject = args.path if args.path else f"git diff {args.diff}"
    header = f"# 评审报告 {stamp}\n\n- 对象：{subject}\n- 模型：{MODEL}\n\n---\n\n"
    target.write_text(header + report, encoding="utf-8")

    print(report)
    print(f"\n报告已保存到：{target}")


if __name__ == "__main__":
    main()
