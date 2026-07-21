"""YOLO形式データセットの目視確認用HTMLを作成する。"""

from __future__ import annotations

import argparse
import html
import os
from pathlib import Path

from prepare_taco_dataset import IMAGE_EXTENSIONS, load_data_yaml_names


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def image_files(image_dir: Path) -> list[Path]:
    return sorted(
        path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def label_summary(label_path: Path, names: list[str]) -> str:
    if not label_path.exists():
        return "label missing"
    labels: list[str] = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 5:
            labels.append("bad label")
            continue
        class_id = int(float(parts[0]))
        class_name = names[class_id] if 0 <= class_id < len(names) else f"unknown:{class_id}"
        labels.append(class_name)
    return ", ".join(labels) if labels else "empty label"


def build_html(raw_dir: Path, output_path: Path, title: str) -> None:
    names = load_data_yaml_names(raw_dir / "data.yaml")
    cards: list[str] = []
    for split in ("train", "valid", "val", "test"):
        image_dir = raw_dir / split / "images"
        label_dir = raw_dir / split / "labels"
        if not image_dir.exists():
            continue
        for image_path in image_files(image_dir):
            rel_image = os.path.relpath(image_path, output_path.parent)
            rel_dataset = image_path.relative_to(raw_dir).as_posix()
            summary = label_summary(label_dir / f"{image_path.stem}.txt", names)
            cards.append(
                "<article class=\"card\">"
                f"<img src=\"{html.escape(rel_image)}\" loading=\"lazy\" alt=\"\">"
                f"<p class=\"filename\">{html.escape(rel_dataset)}</p>"
                f"<p>{html.escape(summary)}</p>"
                "</article>"
            )

    content = f"""<!doctype html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <title>{html.escape(title)}</title>
    <style>
        body {{ font-family: sans-serif; margin: 24px; background: #f6f8fa; color: #1f2933; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
        .card {{ border: 1px solid #d9e2ec; border-radius: 8px; padding: 8px; background: white; }}
        img {{ width: 100%; aspect-ratio: 1 / 1; object-fit: contain; background: #eef2f6; }}
        p {{ margin: 6px 0 0; font-size: 12px; overflow-wrap: anywhere; }}
        .filename {{ font-weight: 700; }}
    </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <p>total images: {len(cards)}</p>
    <div class="grid">
        {''.join(cards)}
    </div>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLOデータセットの確認用HTMLを作成する")
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="YOLO dataset review")
    args = parser.parse_args()

    build_html(args.raw_dir.resolve(), args.output.resolve(), args.title)
    print(f"review_html={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
