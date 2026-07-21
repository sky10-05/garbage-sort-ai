"""dry_battery用allowlistのtrainだけを多様性優先でダウンサンプリングする。"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "batteries"
DEFAULT_INPUT_ALLOWLIST = PROJECT_ROOT / "data" / "config" / "batteries_dry_battery_allowlist.txt"
DEFAULT_OUTPUT_ALLOWLIST = (
    PROJECT_ROOT / "data" / "config" / "batteries_dry_battery_allowlist_balanced.txt"
)


def original_base(image_path: Path) -> str:
    return image_path.name.split(".rf.", 1)[0]


def object_count(raw_dir: Path, rel_image_path: str) -> int:
    image_path = raw_dir / rel_image_path
    split = image_path.parts[-3]
    label_path = raw_dir / split / "labels" / f"{image_path.stem}.txt"
    return sum(1 for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip())


def image_feature(image_path: Path) -> tuple[float, ...]:
    image = Image.open(image_path).convert("RGB").resize((8, 8))
    return tuple(value / 255 for value in image.tobytes())


def feature_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right))


def select_group_representatives(raw_dir: Path, rel_paths: list[str]) -> list[tuple[str, int, tuple[float, ...]]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for rel_path in rel_paths:
        groups[original_base(raw_dir / rel_path)].append(rel_path)

    representatives: list[tuple[str, int, tuple[float, ...]]] = []
    for group_paths in groups.values():
        # Roboflow拡張の中から、ボックス数が少なく扱いやすい代表画像を選ぶ。
        chosen = min(group_paths, key=lambda rel_path: (object_count(raw_dir, rel_path), rel_path))
        representatives.append((chosen, object_count(raw_dir, chosen), image_feature(raw_dir / chosen)))
    return representatives


def diverse_select(
    candidates: list[tuple[str, int, tuple[float, ...]]],
    target_objects: int,
    max_objects: int,
) -> list[str]:
    if not candidates:
        return []

    selected: list[tuple[str, int, tuple[float, ...]]] = []
    remaining = sorted(candidates, key=lambda item: (item[1], item[0]))
    selected.append(remaining.pop(0))
    selected_objects = selected[0][1]

    while remaining and selected_objects < target_objects:
        best_index = -1
        best_score = -1.0
        for index, candidate in enumerate(remaining):
            rel_path, count, feature = candidate
            if selected_objects + count > max_objects:
                continue
            nearest_distance = min(feature_distance(feature, chosen[2]) for chosen in selected)
            # 物体数が少ない画像を少し優先し、見た目の距離も保つ。
            score = nearest_distance / count
            if score > best_score or (score == best_score and rel_path < remaining[best_index][0]):
                best_index = index
                best_score = score

        if best_index < 0:
            break
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        selected_objects += chosen[1]

    return sorted(rel_path for rel_path, _, _ in selected)


def main() -> int:
    parser = argparse.ArgumentParser(description="dry_battery train allowlistを多様性優先で間引く")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--input-allowlist", type=Path, default=DEFAULT_INPUT_ALLOWLIST)
    parser.add_argument("--output-allowlist", type=Path, default=DEFAULT_OUTPUT_ALLOWLIST)
    parser.add_argument("--target-train-objects", type=int, default=250)
    parser.add_argument("--max-train-objects", type=int, default=300)
    args = parser.parse_args()

    allowed = [
        line.strip()
        for line in args.input_allowlist.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    train_paths = [rel_path for rel_path in allowed if rel_path.startswith("train/")]
    eval_paths = [rel_path for rel_path in allowed if not rel_path.startswith("train/")]

    representatives = select_group_representatives(args.raw_dir, train_paths)
    selected_train_paths = diverse_select(
        representatives,
        target_objects=args.target_train_objects,
        max_objects=args.max_train_objects,
    )

    output_paths = sorted(selected_train_paths + eval_paths)
    args.output_allowlist.parent.mkdir(parents=True, exist_ok=True)
    args.output_allowlist.write_text("\n".join(output_paths) + "\n", encoding="utf-8")

    train_objects = sum(object_count(args.raw_dir, rel_path) for rel_path in selected_train_paths)
    eval_objects = sum(object_count(args.raw_dir, rel_path) for rel_path in eval_paths)
    print(f"input_train_images={len(train_paths)}")
    print(f"candidate_train_originals={len(representatives)}")
    print(f"selected_train_images={len(selected_train_paths)}")
    print(f"selected_train_objects={train_objects}")
    print(f"kept_eval_images={len(eval_paths)}")
    print(f"kept_eval_objects={eval_objects}")
    print(f"output_allowlist={args.output_allowlist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
