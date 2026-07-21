"""Ultralytics YOLOでごみ分類用データセットを学習する入口。"""

from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_YAML = PROJECT_ROOT / "data" / "yolo_dataset" / "data.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLOモデルを追加学習する")
    parser.add_argument("--model", default="yolo11n.pt", help="学習元モデル")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_YAML, help="YOLO data.yaml")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default=None, help="例: cpu, 0")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--plots", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "ultralytics が未インストールです。学習前に `pip install ultralytics` "
            "または環境に合わせたインストールを行ってください。"
        ) from exc

    model = YOLO(args.model)
    model.train(
        data=str(args.data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        amp=args.amp,
        plots=args.plots,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
