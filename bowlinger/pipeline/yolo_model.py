"""Load a YOLO detector from models/detectors.json.

The active entry is `BOWLINGER_MODEL`, or the file's `active` key.
Weights are resolved next to the config file. A later cricket model is a new
`.pt` in `models/` plus a class map in that JSON. No code change.

Roles the pipeline understands: person, batsman, bowler, fielder, wicketkeeper, bat, ball, stumps, pads, gloves.
`person` is split into batsman and bowler by where the box sits.
Any role the active map does not name is left for the classic fallback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bowlinger.config import Settings

YOLO_URL = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt"
ROLES = ("person", "batsman", "bowler", "bat", "ball", "stumps")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT.parent / "models" / "detectors.json"


@dataclass
class Detection:
    role: str
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


@dataclass
class ModelSpec:
    name: str
    weights: Path
    confidence: float
    image_size: int
    classes: dict[str, int]
    roles: dict[str, list[str]]
    config_path: Path

    def class_names(self, role: str) -> list[str]:
        return list(self.roles.get(role, []))

    def class_ids(self, role: str) -> list[int]:
        return [self.classes[name] for name in self.class_names(role) if name in self.classes]

    def class_id(self, role: str) -> int | None:
        ids = self.class_ids(role)
        if ids:
            return ids[0]
        if role in ("batsman", "bowler") and self.class_ids("person"):
            return self.class_ids("person")[0]
        return None

    def provides(self, role: str) -> bool:
        if self.class_ids(role):
            return True
        if role in ("batsman", "bowler") and self.class_ids("person"):
            return True
        return False

    def fallback_roles(self) -> list[str]:
        """Roles a custom model has not taken over, so classic CV may fill them."""
        return [role for role in ("bat", "ball", "stumps") if not self.provides(role)]


def config_path(settings: Settings | None = None) -> Path:
    if settings is not None and settings.model_config is not None:
        return Path(settings.model_config)
    return DEFAULT_CONFIG


def _names(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def load_spec(settings: Settings | None = None, name: str | None = None) -> ModelSpec:
    path = config_path(settings)
    data = json.loads(path.read_text())
    detectors = data.get("detectors", {})
    explicit = name or (settings.model_name if settings is not None and settings.model_name else "")
    if explicit:
        chosen = explicit
    else:
        chosen = data.get("active", "coco")
        cricket = detectors.get("cricket")
        if cricket:
            weights = Path(cricket["weights"])
            if not weights.is_absolute():
                weights = path.parent / weights
            if weights.is_file():
                chosen = "cricket"
            elif chosen == "cricket" and "coco" in detectors:
                chosen = "coco"
    try:
        entry = detectors[chosen]
    except KeyError as exc:
        known = ", ".join(sorted(detectors))
        raise KeyError(f"No detector {chosen!r} in {path}. Known: {known}") from exc
    weights = Path(entry["weights"])
    if not weights.is_absolute():
        weights = path.parent / weights
    if not weights.is_file() and chosen != "coco" and "coco" in detectors and not explicit:
        return load_spec(settings, name="coco")
    return ModelSpec(
        name=chosen,
        weights=weights,
        confidence=float(entry.get("confidence", 0.3)),
        image_size=int(entry.get("image_size", 480)),
        classes={str(key): int(value) for key, value in entry.get("classes", {}).items()},
        roles={str(role): _names(class_name) for role, class_name in entry.get("roles", {}).items()},
        config_path=path,
    )


def configure_cpu_threads() -> None:
    """One torch thread per CPU, and one OpenCV thread, so they do not fight."""
    import os

    import cv2
    import torch

    count = max(1, os.cpu_count() or 1)
    torch.set_num_threads(count)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    cv2.setNumThreads(1)


class YoloDetector:
    """One loaded Ultralytics model. Instances are cached per weights path."""

    _cache: dict[str, YoloDetector] = {}
    _threads_ready = False

    def __init__(self, spec: ModelSpec) -> None:
        from ultralytics import YOLO

        if not YoloDetector._threads_ready:
            configure_cpu_threads()
            YoloDetector._threads_ready = True
        self.spec = spec
        self.model = YOLO(str(spec.weights))
        self.fallback = spec.fallback_roles()

    @classmethod
    def for_settings(cls, settings: Settings | None = None) -> YoloDetector:
        spec = load_spec(settings)
        if not spec.weights.is_file():
            raise FileNotFoundError(
                f"Weights for detector {spec.name!r} are not at {spec.weights}. "
                "Drop the .pt next to models/detectors.json or run scripts/download_yolo_weights.py."
            )
        key = str(spec.weights.resolve())
        cached = cls._cache.get(key)
        if (
            cached is None
            or cached.spec.name != spec.name
            or cached.spec.roles != spec.roles
            or cached.spec.image_size != spec.image_size
        ):
            cached = cls(spec)
            cls._cache[key] = cached
        return cached

    def detect(self, frame) -> dict[str, list[Detection]]:
        wanted = sorted({class_id for role in self.spec.roles for class_id in self.spec.class_ids(role)})
        result = self.model.predict(
            frame,
            verbose=False,
            conf=self.spec.confidence,
            classes=wanted or None,
            imgsz=self.spec.image_size,
        )[0]
        grouped: dict[str, list[Detection]] = {role: [] for role in self.spec.roles}
        if result.boxes is None:
            return grouped
        id_to_roles: dict[int, list[tuple[str, str]]] = {}
        for role, class_names in self.spec.roles.items():
            for class_name in class_names:
                class_id = self.spec.classes.get(class_name)
                if class_id is None:
                    continue
                id_to_roles.setdefault(class_id, []).append((role, class_name))
        for box in result.boxes:
            class_id = int(box.cls[0])
            roles = id_to_roles.get(class_id, [])
            x1, y1, x2, y2 = (float(value) for value in box.xyxy[0])
            confidence = float(box.conf[0])
            for role, class_name in roles:
                grouped[role].append(
                    Detection(
                        role=role,
                        class_name=class_name,
                        confidence=confidence,
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                    )
                )
        return grouped
