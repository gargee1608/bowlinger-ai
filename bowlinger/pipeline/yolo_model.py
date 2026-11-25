"""Load a YOLO detector from models/detectors.json.

The active entry is `BOWLINGER_MODEL`, or the file's `active` key.
Weights are resolved next to the config file. A later cricket model is a new
`.pt` in `models/` plus a class map in that JSON. No code change.

Roles the pipeline understands: person, batsman, bowler, bat, ball, stumps.
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
    roles: dict[str, str]
    config_path: Path

    def class_id(self, role: str) -> int | None:
        class_name = self.roles.get(role)
        if class_name is None:
            return None
        return self.classes.get(class_name)

    def provides(self, role: str) -> bool:
        if role in ("batsman", "bowler") and self.class_id(role) is None and self.class_id("person") is not None:
            return True
        return self.class_id(role) is not None

    def fallback_roles(self) -> list[str]:
        """Roles a custom model has not taken over, so classic CV may fill them."""
        return [role for role in ("bat", "ball", "stumps") if not self.provides(role)]


def config_path(settings: Settings | None = None) -> Path:
    if settings is not None and settings.model_config is not None:
        return Path(settings.model_config)
    return DEFAULT_CONFIG


def load_spec(settings: Settings | None = None, name: str | None = None) -> ModelSpec:
    path = config_path(settings)
    data = json.loads(path.read_text())
    chosen = name
    if chosen is None and settings is not None and settings.model_name:
        chosen = settings.model_name
    if not chosen:
        chosen = data.get("active", "coco")
    try:
        entry = data["detectors"][chosen]
    except KeyError as exc:
        known = ", ".join(sorted(data.get("detectors", {})))
        raise KeyError(f"No detector {chosen!r} in {path}. Known: {known}") from exc
    weights = Path(entry["weights"])
    if not weights.is_absolute():
        weights = path.parent / weights
    return ModelSpec(
        name=chosen,
        weights=weights,
        confidence=float(entry.get("confidence", 0.3)),
        image_size=int(entry.get("image_size", 480)),
        classes={str(key): int(value) for key, value in entry.get("classes", {}).items()},
        roles={str(role): str(class_name) for role, class_name in entry.get("roles", {}).items()},
        config_path=path,
    )


class YoloDetector:
    """One loaded Ultralytics model. Instances are cached per weights path."""

    _cache: dict[str, YoloDetector] = {}

    def __init__(self, spec: ModelSpec) -> None:
        from ultralytics import YOLO

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
        if cached is None or cached.spec.name != spec.name or cached.spec.roles != spec.roles:
            cached = cls(spec)
            cls._cache[key] = cached
        return cached

    def detect(self, frame) -> dict[str, list[Detection]]:
        wanted = sorted({self.spec.classes[name] for name in self.spec.roles.values() if name in self.spec.classes})
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
        id_to_roles: dict[int, list[str]] = {}
        for role, class_name in self.spec.roles.items():
            class_id = self.spec.classes.get(class_name)
            if class_id is None:
                continue
            id_to_roles.setdefault(class_id, []).append(role)
        for box in result.boxes:
            class_id = int(box.cls[0])
            roles = id_to_roles.get(class_id, [])
            x1, y1, x2, y2 = (float(value) for value in box.xyxy[0])
            confidence = float(box.conf[0])
            for role in roles:
                grouped[role].append(
                    Detection(
                        role=role,
                        class_name=self.spec.roles[role],
                        confidence=confidence,
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                    )
                )
        return grouped
