"""Place the Roboflow cricket detection export where training expects it.

The images are not stored in this repository. The export is
jignesh-workspace/cricket-object-detection-qnjwo version 2 from Roboflow
Universe, license CC BY 4.0:

https://universe.roboflow.com/jignesh-workspace/cricket-object-detection-qnjwo/dataset/2

Download the YOLOv11 (or YOLOv8) zip yourself, then:

    python scripts/fetch_cricket_dataset.py /path/to/export.zip

That unpacks to ~/cricket_dataset with data.yaml, train/, valid/ and test/.
Polygon rows are converted to detection boxes so Ultralytics can train.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

DEST = Path.home() / "cricket_dataset"


def _boxes(text: str) -> str:
    lines = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        if len(parts) == 5:
            lines.append(line.strip())
            continue
        nums = [float(value) for value in parts[1:]]
        if len(nums) < 6 or len(nums) % 2:
            continue
        xs, ys = nums[0::2], nums[1::2]
        x0, x1 = max(0.0, min(xs)), min(1.0, max(xs))
        y0, y1 = max(0.0, min(ys)), min(1.0, max(ys))
        lines.append(f"{parts[0]} {(x0+x1)/2:.6f} {(y0+y1)/2:.6f} {max(1e-6, x1-x0):.6f} {max(1e-6, y1-y0):.6f}")
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/fetch_cricket_dataset.py EXPORT.zip")
    archive = Path(sys.argv[1])
    DEST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(DEST)
    for label in DEST.glob("*/*/labels/*.txt"):
        label.write_text(_boxes(label.read_text()))
    yaml = DEST / "data.yaml"
    if yaml.is_file():
        text = yaml.read_text()
        text = text.replace("train: ../train/images", "train: train/images")
        text = text.replace("val: ../valid/images", "val: valid/images")
        text = text.replace("test: ../test/images", "test: test/images")
        if not text.startswith("path:"):
            text = f"path: {DEST}\n" + text
        yaml.write_text(text)
    print(DEST)


if __name__ == "__main__":
    main()
