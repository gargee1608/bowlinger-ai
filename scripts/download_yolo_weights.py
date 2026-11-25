"""Download the active detector's weights when the file is not already in models/."""

import urllib.request

from bowlinger.pipeline.yolo_model import YOLO_URL, load_spec

# Only the shipped COCO nano model has a public URL. Custom weights are copied in by hand.
KNOWN_URLS = {"yolo11n.pt": YOLO_URL}


def main() -> None:
    spec = load_spec()
    if spec.weights.is_file():
        print(spec.weights, spec.weights.stat().st_size)
        return
    url = KNOWN_URLS.get(spec.weights.name)
    if url is None:
        raise SystemExit(f"No download URL for {spec.weights.name}. Copy that file into {spec.weights.parent}.")
    spec.weights.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, spec.weights)
    print(spec.weights, spec.weights.stat().st_size)


if __name__ == "__main__":
    main()
