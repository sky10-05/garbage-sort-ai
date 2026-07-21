"""YOLOを使ったごみ画像認識処理。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "runs" / "detect" / "train-9" / "weights" / "best.pt"

CLASS_NAMES = {
    0: "plastic_bottle",
    1: "drink_can",
    2: "glass_bottle",
    3: "aerosol_can",
    4: "dry_battery",
}


class ModelLoadError(RuntimeError):
    """YOLOモデルを読み込めない場合の例外。"""


class InferenceError(RuntimeError):
    """YOLO推論に失敗した場合の例外。"""


@dataclass(frozen=True)
class DetectionResult:
    label: str
    display_name: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "display_name": self.display_name,
            "confidence": self.confidence,
        }


_MODEL_CACHE: Any | None = None
_MODEL_CACHE_PATH: Path | None = None


def get_model_path() -> Path:
    """環境変数があれば優先し、なければ試験学習済みモデルを使う。"""
    return Path(os.environ.get("YOLO_MODEL_PATH", DEFAULT_MODEL_PATH)).expanduser().resolve()


def predict_image(image_path: str | Path, model_path: str | Path | None = None) -> dict[str, Any]:
    """画像から最も信頼度の高い検出結果を返す。"""
    resolved_model_path = Path(model_path).expanduser().resolve() if model_path else get_model_path()
    model = _load_model(resolved_model_path)

    try:
        results = model.predict(source=str(image_path), verbose=False)
    except Exception as exc:
        raise InferenceError("YOLO推論に失敗しました。") from exc

    detections = _extract_detections(results)
    if not detections:
        return {
            "label": "unknown",
            "display_name": "判定できないごみ",
            "confidence": 0.0,
        }

    best = max(detections, key=lambda item: item.confidence)
    return best.to_dict()


def _load_model(model_path: Path) -> Any:
    global _MODEL_CACHE, _MODEL_CACHE_PATH

    if _MODEL_CACHE is not None and _MODEL_CACHE_PATH == model_path:
        return _MODEL_CACHE

    if not model_path.exists():
        raise ModelLoadError(f"YOLOモデルが見つかりません: {model_path}")

    os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".tmp" / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(PROJECT_ROOT / ".tmp" / "cache"))

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ModelLoadError("ultralytics がインストールされていません。") from exc

    try:
        _MODEL_CACHE = YOLO(str(model_path))
        _MODEL_CACHE_PATH = model_path
    except Exception as exc:
        raise ModelLoadError("YOLOモデルの読み込みに失敗しました。") from exc
    return _MODEL_CACHE


def _extract_detections(results: Any) -> list[DetectionResult]:
    detections: list[DetectionResult] = []
    for result in results:
        names = getattr(result, "names", CLASS_NAMES) or CLASS_NAMES
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            class_id = int(box.cls.item())
            confidence = float(box.conf.item())
            label = names.get(class_id, CLASS_NAMES.get(class_id, "unknown"))
            detections.append(
                DetectionResult(
                    label=label,
                    display_name=_display_name(label),
                    confidence=confidence,
                )
            )
    return detections


def _display_name(label: str) -> str:
    display_names = {
        "plastic_bottle": "ペットボトル",
        "drink_can": "飲料缶",
        "glass_bottle": "ガラスびん",
        "aerosol_can": "スプレー缶",
        "dry_battery": "乾電池",
    }
    return display_names.get(label, label)
