"""複数のYOLO形式データセットから学習対象5クラスだけを安全に統合する。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "yolo_dataset"

OUTPUT_CLASS_NAMES = [
    "plastic_bottle",
    "drink_can",
    "glass_bottle",
    "aerosol_can",
    "dry_battery",
]

OUTPUT_ID_BY_NAME = {name: index for index, name in enumerate(OUTPUT_CLASS_NAMES)}

SPLIT_MAP = {
    "train": "train",
    "valid": "val",
    "val": "val",
    "test": "test",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class DatasetConfig:
    key: str
    root_name: str
    class_map: dict[str, str]
    enabled: bool
    skip_reason: str = ""
    requires_allowlist: bool = False
    resplit_output: bool = False


DATASET_CONFIGS = [
    DatasetConfig(
        key="taco",
        root_name="taco",
        class_map={
            "Clear plastic bottle": "plastic_bottle",
            "Drink can": "drink_can",
            "Glass bottle": "glass_bottle",
            "Aerosol": "aerosol_can",
            "Battery": "dry_battery",
        },
        enabled=True,
    ),
    DatasetConfig(
        key="trash_detection",
        root_name="trash_detection",
        class_map={},
        enabled=False,
        skip_reason=(
            "クラスがGlass/Metal/Paper/Plastic/Wasteの大分類で、"
            "aerosol_canやdrink_canを一意に取り出せないため自動統合しない"
        ),
    ),
    DatasetConfig(
        key="batteries",
        root_name="batteries",
        class_map={"Battery - v4 2024-07-14 9-11pm": "dry_battery"},
        enabled=True,
        requires_allowlist=True,
        skip_reason=(
            "Batteryクラスに9V電池、ボタン電池、バッテリーパック等が混ざるため、"
            "乾電池と目視確認した画像だけallowlistで統合する"
        ),
    ),
    DatasetConfig(
        key="spray_can",
        root_name="spray_can",
        class_map={"spray can": "aerosol_can"},
        enabled=True,
        requires_allowlist=True,
        resplit_output=True,
        skip_reason=(
            "spray canクラスにLED、トリガー式ボトル、ポンプ式ボトル等が混ざるため、"
            "エアゾール缶と目視確認した画像だけallowlistで統合する"
        ),
    ),
    DatasetConfig(
        key="glass_bottle_extra",
        root_name="glass_bottle",
        class_map={
            "brown_glass_bottle": "glass_bottle",
            "clear_glass_bottle": "glass_bottle",
            "glass bottle": "glass_bottle",
        },
        enabled=True,
        requires_allowlist=True,
        skip_reason="glass_bottle補強用に、採用基準を満たす画像だけallowlistで統合する",
    ),
    DatasetConfig(
        key="plastic_bottles_extra",
        root_name="plastic_bottles",
        class_map={"plastic-bottle": "plastic_bottle"},
        enabled=True,
        requires_allowlist=True,
        skip_reason="plastic_bottle補強用に、飲料用ペットボトルとして使える画像だけallowlistで統合する",
    ),
]


def load_data_yaml_names(data_yaml_path: Path) -> list[str]:
    """PyYAMLが無い環境でもRoboflow形式のnamesを読めるようにする。"""
    text = data_yaml_path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        names = loaded.get("names", [])
        if isinstance(names, dict):
            return [names[index] for index in sorted(names)]
        if isinstance(names, list):
            return [str(name) for name in names]
    except Exception:
        pass

    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("names:"):
            value = stripped.split(":", 1)[1].strip()
            if value.startswith("["):
                return [str(name) for name in ast.literal_eval(value)]

            names: dict[int, str] = {}
            for subline in lines[index + 1 :]:
                if not subline.startswith(" "):
                    break
                key, _, raw_value = subline.strip().partition(":")
                if key.isdigit():
                    names[int(key)] = raw_value.strip().strip("'\"")
            if names:
                return [names[key] for key in sorted(names)]

    raise ValueError(f"クラス一覧を読み取れませんでした: {data_yaml_path}")


def find_source_splits(raw_dir: Path) -> dict[str, str]:
    splits: dict[str, str] = {}
    for source_split, output_split in SPLIT_MAP.items():
        if (raw_dir / source_split / "images").exists() and (raw_dir / source_split / "labels").exists():
            splits[source_split] = output_split
    return splits


def image_files_by_stem(image_dir: Path) -> dict[str, Path]:
    return {
        image_path.stem: image_path
        for image_path in image_dir.iterdir()
        if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS
    }


def parse_label_line(line: str, label_path: Path, line_number: int) -> tuple[int, list[str]]:
    parts = line.split()
    if len(parts) < 5:
        raise ValueError(f"ラベル形式が不正です: {label_path}:{line_number}")
    return int(parts[0]), parts[1:]


def load_allowlist(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()

    allowed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        allowed.add(value)
        allowed.add(Path(value).name)
        allowed.add(Path(value).stem)
    return allowed


def is_allowlisted(image_path: Path, dataset_root: Path, allowlist: set[str]) -> bool:
    if not allowlist:
        return False

    rel = image_path.relative_to(dataset_root).as_posix()
    return rel in allowlist or image_path.name in allowlist or image_path.stem in allowlist


def reset_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        for child in output_dir.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    for output_split in ("train", "val", "test"):
        (output_dir / "images" / output_split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / output_split).mkdir(parents=True, exist_ok=True)


def stable_resplit_output_split(value: str) -> str:
    bucket = int(hashlib.sha256(value.encode("utf-8")).hexdigest(), 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "val"
    return "test"


def write_output_yaml(output_dir: Path) -> None:
    lines = [
        f"path: {output_dir.resolve().as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "",
        "names:",
    ]
    lines.extend(f"  {index}: {name}" for index, name in enumerate(OUTPUT_CLASS_NAMES))
    (output_dir / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_source_to_output_id(
    source_names: list[str],
    class_map: dict[str, str],
) -> tuple[dict[int, int], list[str]]:
    normalized_to_id = {name.strip().lower(): class_id for class_id, name in enumerate(source_names)}
    mapping: dict[int, int] = {}
    missing: list[str] = []

    for source_name, output_name in class_map.items():
        source_id = normalized_to_id.get(source_name.strip().lower())
        if source_id is None:
            missing.append(source_name)
            continue
        mapping[source_id] = OUTPUT_ID_BY_NAME[output_name]

    return mapping, missing


def collect_dataset_summary(
    dataset_root: Path,
    source_splits: dict[str, str],
) -> tuple[dict[str, dict[str, int]], dict[str, Counter[int]]]:
    split_counts: dict[str, dict[str, int]] = {}
    object_counts: dict[str, Counter[int]] = {}

    for source_split in source_splits:
        image_dir = dataset_root / source_split / "images"
        label_dir = dataset_root / source_split / "labels"
        split_counts[source_split] = {
            "images": sum(1 for path in image_dir.iterdir() if path.is_file()),
            "labels": sum(1 for path in label_dir.glob("*.txt")),
        }

        counter: Counter[int] = Counter()
        for label_path in label_dir.glob("*.txt"):
            for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip():
                    class_id, _ = parse_label_line(line, label_path, line_number)
                    counter[class_id] += 1
        object_counts[source_split] = counter

    return split_counts, object_counts


def copy_filtered_dataset(
    config: DatasetConfig,
    dataset_root: Path,
    output_dir: Path,
    source_splits: dict[str, str],
    source_to_output_id: dict[int, int],
    allowlist: set[str],
) -> tuple[dict[str, Counter[int]], dict[str, Counter[int]], dict[str, set[str]], list[str]]:
    output_image_counts: dict[str, Counter[int]] = defaultdict(Counter)
    output_object_counts: dict[str, Counter[int]] = defaultdict(Counter)
    copied_images: dict[str, set[str]] = defaultdict(set)
    warnings: list[str] = []

    for source_split, output_split in source_splits.items():
        source_image_dir = dataset_root / source_split / "images"
        source_label_dir = dataset_root / source_split / "labels"
        source_images = image_files_by_stem(source_image_dir)

        for label_path in sorted(source_label_dir.glob("*.txt")):
            source_image_path = source_images.get(label_path.stem)
            if source_image_path is None:
                warnings.append(f"{config.key}: 画像が見つからないためスキップ: {label_path}")
                continue

            if config.requires_allowlist and not is_allowlisted(source_image_path, dataset_root, allowlist):
                continue

            remapped_lines: list[str] = []
            label_output_ids: set[int] = set()
            label_object_counts: Counter[int] = Counter()
            for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                source_id, values = parse_label_line(line, label_path, line_number)
                if source_id not in source_to_output_id:
                    continue
                output_id = source_to_output_id[source_id]
                remapped_lines.append(" ".join([str(output_id), *values[:4]]))
                label_output_ids.add(output_id)
                label_object_counts[output_id] += 1

            if not remapped_lines:
                continue

            rel_image_path = source_image_path.relative_to(dataset_root).as_posix()
            effective_output_split = (
                stable_resplit_output_split(rel_image_path)
                if config.resplit_output
                else output_split
            )
            output_image_dir = output_dir / "images" / effective_output_split
            output_label_dir = output_dir / "labels" / effective_output_split
            safe_stem = f"{config.key}__{source_split}__{source_image_path.stem}"
            output_image_name = f"{safe_stem}{source_image_path.suffix.lower()}"
            output_label_name = f"{safe_stem}.txt"
            shutil.copy2(source_image_path, output_image_dir / output_image_name)
            (output_label_dir / output_label_name).write_text(
                "\n".join(remapped_lines) + "\n",
                encoding="utf-8",
            )
            copied_images[effective_output_split].add(output_image_name)
            for output_id in label_output_ids:
                output_image_counts[effective_output_split][output_id] += 1
            output_object_counts[effective_output_split].update(label_object_counts)

    return output_image_counts, output_object_counts, copied_images, warnings


def merge_counter_dicts(target: dict[str, Counter[int]], source: dict[str, Counter[int]]) -> None:
    for split, counter in source.items():
        target[split].update(counter)


def merge_set_dicts(target: dict[str, set[str]], source: dict[str, set[str]]) -> None:
    for split, values in source.items():
        target[split].update(values)


def validate_output_dataset(output_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    image_hashes: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for split in ("train", "val", "test"):
        image_dir = output_dir / "images" / split
        label_dir = output_dir / "labels" / split
        images = image_files_by_stem(image_dir)
        labels = {path.stem: path for path in label_dir.glob("*.txt")}

        if not images:
            errors.append(f"{split}: 画像がありません")
        if not labels:
            errors.append(f"{split}: ラベルがありません")

        for stem, label_path in labels.items():
            text = label_path.read_text(encoding="utf-8").strip()
            if not text:
                errors.append(f"空のラベルファイルがあります: {label_path}")
                continue
            if stem not in images:
                errors.append(f"ラベルに対応する画像がありません: {label_path}")

            for line_number, line in enumerate(text.splitlines(), 1):
                class_id, _ = parse_label_line(line, label_path, line_number)
                if class_id < 0 or class_id >= len(OUTPUT_CLASS_NAMES):
                    errors.append(f"クラスIDが範囲外です: {label_path}:{line_number}")

        for stem, image_path in images.items():
            if stem not in labels:
                errors.append(f"画像に対応するラベルがありません: {image_path}")
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            image_hashes[digest].append((split, image_path.name))

    cross_split_duplicates = [
        values for values in image_hashes.values() if len({split for split, _ in values}) > 1
    ]
    if cross_split_duplicates:
        warnings.append(f"画像ハッシュが複数分割で重複しています: {len(cross_split_duplicates)}件")

    return {
        "errors": errors,
        "warnings": warnings,
        "cross_split_duplicate_hashes": len(cross_split_duplicates),
    }


def prepare_dataset(
    raw_root: Path,
    output_dir: Path,
    battery_allowlist: Path | None,
    spray_can_allowlist: Path | None,
    glass_bottle_allowlist: Path | None,
    plastic_bottle_allowlist: Path | None,
) -> dict[str, object]:
    reset_output_dir(output_dir)
    write_output_yaml(output_dir)

    allowlist_values_by_key = {
        "batteries": load_allowlist(battery_allowlist),
        "spray_can": load_allowlist(spray_can_allowlist),
        "glass_bottle_extra": load_allowlist(glass_bottle_allowlist),
        "plastic_bottles_extra": load_allowlist(plastic_bottle_allowlist),
    }
    dataset_reports: list[dict[str, object]] = []
    total_output_image_counts: dict[str, Counter[int]] = defaultdict(Counter)
    total_output_object_counts: dict[str, Counter[int]] = defaultdict(Counter)
    total_copied_images: dict[str, set[str]] = defaultdict(set)
    warnings: list[str] = []

    for config in DATASET_CONFIGS:
        dataset_root = raw_root / config.root_name
        report: dict[str, object] = {
            "key": config.key,
            "root": dataset_root,
            "enabled": config.enabled,
            "skip_reason": config.skip_reason,
            "class_names": [],
            "source_splits": {},
            "split_counts": {},
            "source_object_counts": {},
            "mapping": {},
            "missing_mapping": [],
            "extracted_image_counts": defaultdict(Counter),
            "extracted_object_counts": defaultdict(Counter),
            "copied_images": defaultdict(set),
        }

        if not dataset_root.exists():
            report["skip_reason"] = f"データセットフォルダが見つかりません: {dataset_root}"
            dataset_reports.append(report)
            continue

        data_yaml_path = dataset_root / "data.yaml"
        if not data_yaml_path.exists():
            report["skip_reason"] = f"data.yamlが見つかりません: {data_yaml_path}"
            dataset_reports.append(report)
            continue

        source_names = load_data_yaml_names(data_yaml_path)
        source_splits = find_source_splits(dataset_root)
        split_counts, source_object_counts = collect_dataset_summary(dataset_root, source_splits)
        source_to_output_id, missing_mapping = build_source_to_output_id(source_names, config.class_map)

        report.update(
            {
                "class_names": source_names,
                "source_splits": source_splits,
                "split_counts": split_counts,
                "source_object_counts": source_object_counts,
                "mapping": source_to_output_id,
                "missing_mapping": missing_mapping,
            }
        )

        should_extract = config.enabled and bool(source_to_output_id)
        allowlist_values = allowlist_values_by_key.get(config.key, set())
        if config.requires_allowlist and not allowlist_values:
            should_extract = False
            report["skip_reason"] = config.skip_reason

        if should_extract:
            image_counts, object_counts, copied_images, copy_warnings = copy_filtered_dataset(
                config=config,
                dataset_root=dataset_root,
                output_dir=output_dir,
                source_splits=source_splits,
                source_to_output_id=source_to_output_id,
                allowlist=allowlist_values,
            )
            report["extracted_image_counts"] = image_counts
            report["extracted_object_counts"] = object_counts
            report["copied_images"] = copied_images
            merge_counter_dicts(total_output_image_counts, image_counts)
            merge_counter_dicts(total_output_object_counts, object_counts)
            merge_set_dicts(total_copied_images, copied_images)
            warnings.extend(copy_warnings)

        dataset_reports.append(report)

    validation = validate_output_dataset(output_dir)

    return {
        "dataset_reports": dataset_reports,
        "output_image_counts": total_output_image_counts,
        "output_object_counts": total_output_object_counts,
        "copied_images": total_copied_images,
        "warnings": warnings,
        "validation": validation,
        "battery_allowlist": battery_allowlist,
        "battery_allowlist_count": len(allowlist_values_by_key["batteries"]),
        "spray_can_allowlist": spray_can_allowlist,
        "spray_can_allowlist_count": len(allowlist_values_by_key["spray_can"]),
        "glass_bottle_allowlist": glass_bottle_allowlist,
        "glass_bottle_allowlist_count": len(allowlist_values_by_key["glass_bottle_extra"]),
        "plastic_bottle_allowlist": plastic_bottle_allowlist,
        "plastic_bottle_allowlist_count": len(allowlist_values_by_key["plastic_bottles_extra"]),
    }


def print_report(result: dict[str, object], output_dir: Path) -> None:
    print("== データセット別の確認結果 ==")
    for report in result["dataset_reports"]:
        key = report["key"]
        class_names = report["class_names"]
        source_splits = report["source_splits"]
        split_counts = report["split_counts"]
        mapping = report["mapping"]
        source_object_counts = report["source_object_counts"]
        extracted_object_counts = report["extracted_object_counts"]
        extracted_image_counts = report["extracted_image_counts"]
        copied_images = report["copied_images"]
        skip_reason = report["skip_reason"]

        print(f"\n[{key}]")
        if skip_reason:
            print(f"判断: {skip_reason}")
        if not class_names:
            continue

        print("元クラス一覧:")
        for class_id, class_name in enumerate(class_names):
            print(f"  {class_id}: {class_name}")

        print("分割:")
        for source_split, output_split in source_splits.items():
            counts = split_counts[source_split]
            print(f"  {source_split} -> {output_split}: images={counts['images']}, labels={counts['labels']}")

        print("対象クラス対応:")
        if mapping:
            for source_id, output_id in sorted(mapping.items(), key=lambda item: item[1]):
                print(f"  {source_id}:{class_names[source_id]} -> {output_id}:{OUTPUT_CLASS_NAMES[output_id]}")
        else:
            print("  対応なし")

        print("元データ内の対象候補物体数:")
        for source_split in source_splits:
            print(f"  [{source_split}]")
            for source_id, output_id in sorted(mapping.items(), key=lambda item: item[1]):
                count = source_object_counts[source_split][source_id]
                print(f"    {OUTPUT_CLASS_NAMES[output_id]}: objects={count}")

        print("抽出件数:")
        for output_split in ("train", "val", "test"):
            total_images = len(copied_images[output_split])
            total_objects = sum(extracted_object_counts[output_split].values())
            print(f"  [{output_split}] images={total_images}, objects={total_objects}")
            for output_id, output_name in enumerate(OUTPUT_CLASS_NAMES):
                print(
                    f"    {output_name}: "
                    f"images={extracted_image_counts[output_split][output_id]}, "
                    f"objects={extracted_object_counts[output_split][output_id]}"
                )

    print("\n== 統合後データセット ==")
    output_image_counts = result["output_image_counts"]
    output_object_counts = result["output_object_counts"]
    copied_images = result["copied_images"]
    for output_split in ("train", "val", "test"):
        total_images = len(copied_images[output_split])
        total_objects = sum(output_object_counts[output_split].values())
        print(f"[{output_split}] images={total_images}, objects={total_objects}")
        for output_id, output_name in enumerate(OUTPUT_CLASS_NAMES):
            print(
                f"  {output_name}: "
                f"images={output_image_counts[output_split][output_id]}, "
                f"objects={output_object_counts[output_split][output_id]}"
            )

    if result["warnings"]:
        print("\n== 抽出時の警告 ==")
        for warning in result["warnings"]:
            print(f"- {warning}")

    print("\n== 検証結果 ==")
    validation = result["validation"]
    if not validation["errors"] and not validation["warnings"]:
        print("OK: 学習用YOLOデータセットとして基本チェックを通過しました。")
    for error in validation["errors"]:
        print(f"ERROR: {error}")
    for warning in validation["warnings"]:
        print(f"WARNING: {warning}")
    print(f"cross_split_duplicate_hashes={validation['cross_split_duplicate_hashes']}")

    print("\n== 学習コマンド例 ==")
    print(
        "yolo detect train "
        "model=yolo11n.pt "
        f"data={output_dir / 'data.yaml'} "
        "epochs=50 imgsz=640 batch=8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLOデータセットを5クラスに統合する")
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--battery-allowlist",
        type=Path,
        default=None,
        help="乾電池と目視確認したBatteries画像のパス、ファイル名、またはstemを1行ずつ書いたファイル",
    )
    parser.add_argument(
        "--spray-can-allowlist",
        type=Path,
        default=None,
        help="エアゾール缶と目視確認したspray can画像のパス、ファイル名、またはstemを1行ずつ書いたファイル",
    )
    parser.add_argument(
        "--glass-bottle-allowlist",
        type=Path,
        default=None,
        help="ガラスびんとして利用するGlass Bottle画像のパス、ファイル名、またはstemを1行ずつ書いたファイル",
    )
    parser.add_argument(
        "--plastic-bottle-allowlist",
        type=Path,
        default=None,
        help="ペットボトルとして利用するPlastic Bottle画像のパス、ファイル名、またはstemを1行ずつ書いたファイル",
    )
    args = parser.parse_args()

    result = prepare_dataset(
        raw_root=args.raw_root.resolve(),
        output_dir=args.output_dir.resolve(),
        battery_allowlist=args.battery_allowlist.resolve() if args.battery_allowlist else None,
        spray_can_allowlist=args.spray_can_allowlist.resolve() if args.spray_can_allowlist else None,
        glass_bottle_allowlist=args.glass_bottle_allowlist.resolve() if args.glass_bottle_allowlist else None,
        plastic_bottle_allowlist=args.plastic_bottle_allowlist.resolve() if args.plastic_bottle_allowlist else None,
    )
    print_report(result, args.output_dir.resolve())

    validation = result["validation"]
    return 1 if validation["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
