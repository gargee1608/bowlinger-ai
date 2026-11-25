FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# yolo11n.pt can be re-downloaded. cricket.pt is Git LFS and must already be
# the real file in the build context (git lfs pull before compose build).
RUN python - << 'PY'
from pathlib import Path
import urllib.request

yolo = Path("models/yolo11n.pt")
cricket = Path("models/cricket.pt")
url = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt"

def pointer(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1_000_000:
        return True
    return path.read_bytes()[:40].startswith(b"version https://git-lfs")

yolo.parent.mkdir(parents=True, exist_ok=True)
if pointer(yolo):
    urllib.request.urlretrieve(url, yolo)
if pointer(cricket):
    raise SystemExit(
        "models/cricket.pt is missing or still a Git LFS pointer. "
        "Run git lfs pull, then docker compose build again."
    )
print("weights", yolo.stat().st_size, cricket.stat().st_size)
PY

ENV PYTHONPATH=/app \
    BOWLINGER_DATA=/data \
    BOWLINGER_DB=/var/lib/bowlinger/bowlinger.db \
    BOWLINGER_HOST=0.0.0.0 \
    BOWLINGER_PORT=8741

EXPOSE 8741
VOLUME ["/data", "/var/lib/bowlinger"]
CMD ["python", "-m", "bowlinger"]
