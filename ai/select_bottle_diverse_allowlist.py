"""glass_bottle/plastic_bottle補強用allowlistを多様性優先で作成する。"""

from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from pathlib import Path

from prepare_taco_dataset import IMAGE_EXTENSIONS, load_data_yaml_names


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def image_files(image_dir: Path) -> list[Path]:
    return sorted(
        path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def original_base(image_path: Path) -> str:
    return image_path.name.split(".rf.", 1)[0]


def feature_distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right))


def parse_label(label_path: Path, target_ids: set[int]) -> tuple[int, tuple[float, ...]]:
    count = 0
    features: list[float] = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        class_id = int(float(parts[0]))
        if class_id in target_ids:
            count += 1
            x, y, width, height = (float(value) for value in parts[1:5])
            features.extend([class_id / 10, x, y, width, height, width / max(height, 0.001)])
    if not features:
        return 0, (0.0,)
    return count, tuple(features[:18])


def collect_candidates(
    raw_dir: Path,
    split: str,
    target_ids: set[int],
    max_candidates: int,
) -> tuple[list[tuple[str, int, tuple[float, ...]]], int]:
    image_dir = raw_dir / split / "images"
    label_dir = raw_dir / split / "labels"
    if not image_dir.exists() or not label_dir.exists():
        return [], 0

    grouped: dict[str, list[Path]] = defaultdict(list)
    for image_path in image_files(image_dir):
        label_path = label_dir / f"{image_path.stem}.txt"
        if not label_path.exists() or parse_label(label_path, target_ids)[0] <= 0:
            continue
        grouped[original_base(image_path)].append(image_path)

    group_items = sorted(
        grouped.values(),
        key=lambda paths: hashlib.sha256(original_base(paths[0]).encode("utf-8")).hexdigest(),
    )
    original_candidate_count = len(group_items)
    candidates: list[tuple[str, int, tuple[float, ...]]] = []
    for group_paths in group_items[:max_candidates]:
        chosen = min(
            group_paths,
            key=lambda path: (parse_label(label_dir / f"{path.stem}.txt", target_ids)[0], path.name),
        )
        rel_path = chosen.relative_to(raw_dir).as_posix()
        object_count, feature = parse_label(label_dir / f"{chosen.stem}.txt", target_ids)
        candidates.append((rel_path, object_count, feature))
    return candidates, original_candidate_count


def diverse_select(candidates: list[tuple[str, int, tuple[float, ...]]], target_objects: int) -> list[str]:
    if not candidates or target_objects <= 0:
        return []

    selected: list[tuple[str, int, tuple[float, ...]]] = []
    remaining = sorted(candidates, key=lambda item: (item[1], item[0]))
    selected.append(remaining.pop(0))
    selected_objects = selected[0][1]

    while remaining and selected_objects < target_objects:
        best_index = 0
        best_score = -1.0
        for index, candidate in enumerate(remaining):
            _, count, feature = candidate
            nearest_distance = min(feature_distance(feature, chosen[2]) for chosen in selected)
            score = nearest_distance / max(count, 1)
            if score > best_score:
                best_index = index
                best_score = score
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        selected_objects += chosen[1]

    return sorted(rel_path for rel_path, _, _ in selected)


def write_allowlist(output_path: Path, rel_paths: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(sorted(rel_paths)) + "\n", encoding="utf-8")


def class_ids(raw_dir: Path, target_class_names: list[str]) -> set[int]:
    names = load_data_yaml_names(raw_dir / "data.yaml")
    normalized_targets = {name.strip().lower() for name in target_class_names}
    return {index for index, name in enumerate(names) if name.strip().lower() in normalized_targets}


def main() -> int:
    parser = argparse.ArgumentParser(description="追加ボトル系データセットのallowlistを作成する")
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--target-class", action="append", required=True)
    parser.add_argument("--output-allowlist", type=Path, required=True)
    parser.add_argument("--train-target-objects", type=int, required=True)
    parser.add_argument("--val-target-objects", type=int, default=40)
    parser.add_argument("--test-target-objects", type=int, default=40)
    parser.add_argument("--max-candidates-per-split", type=int, default=1200)
    args = parser.parse_args()

    raw_dir = args.raw_dir.resolve()
    target_ids = class_ids(raw_dir, args.target_class)
    if not target_ids:
        raise SystemExit(f"対象クラスが見つかりません: {args.target_class}")

    selected: list[str] = []
    split_targets = {
        "train": args.train_target_objects,
        "valid": args.val_target_objects,
        "val": args.val_target_objects,
        "test": args.test_target_objects,
    }
    for split, target_objects in split_targets.items():
        candidates, original_candidate_count = collect_candidates(
            raw_dir,
            split,
            target_ids,
            args.max_candidates_per_split,
        )
        if not candidates:
            continue
        selected_paths = diverse_select(candidates, target_objects)
        selected.extend(selected_paths)
        selected_objects = sum(count for rel_path, count, _ in candidates if rel_path in set(selected_paths))
        print(
            f"{split}: candidates={original_candidate_count}, limited_candidates={len(candidates)}, "
            f"selected_images={len(selected_paths)}, selected_objects={selected_objects}"
        )

    write_allowlist(args.output_allowlist, selected)
    print(f"output_allowlist={args.output_allowlist}")
    print(f"total_selected_images={len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
