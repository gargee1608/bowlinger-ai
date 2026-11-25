# BOWLINGER AI V1

Local cricket video analysis. Upload a clip, or run the anonymous demo. Analysis is a background job on a session id, so you can close the page and open the result later.

Each delivery reports release, ball track, bat and batsman, bat-ball contact, a shot name, and a virtual run estimate. Real phone clips live in `Sample/`. Status and open decisions are in [BOWLINGER_V1_GOALS.md](BOWLINGER_V1_GOALS.md).

## Requirements

- Python 3.11+
- ffmpeg on `PATH` (clip writing, probe, and audio decode)
- Docker, only if you use Compose

## Run with Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m bowlinger
```

The app listens on port **8741**: [http://127.0.0.1:8741](http://127.0.0.1:8741). Videos and `bowlinger.db` go in `./data`.

## Run with Docker Compose

```bash
docker compose up -d --build
```

Port **8741** is published on `0.0.0.0`. Uploaded videos and the SQLite database are in separate volumes (`bowlinger-videos` and `bowlinger-db`), and the container restarts unless you stop it. Server install, update, Tailscale, and Cloudflare Tunnel steps are in [DEPLOY.md](DEPLOY.md).

## Upload a video

Open the site, choose a clip, and start analysis. The page polls until the session is `completed` or `failed`.

```bash
curl -s -F "video=@clip.mp4" -F "user_key=coach_1" http://127.0.0.1:8741/api/sessions
curl -s http://127.0.0.1:8741/api/sessions/SESSION_ID
```

The upload returns a `session_id`. A direct page for that session is `http://127.0.0.1:8741/s/SESSION_ID`. You can close the browser and fetch that URL later. Anyone with the id can read the session.

Leave `user_key` out and the response includes a new anonymous key (`anon_…`). Send that key on later uploads to keep the same storage budget.

## Anonymous demo

```bash
curl -s -X POST http://127.0.0.1:8741/api/demo
curl -s http://127.0.0.1:8741/api/users/USER_KEY
```

The demo builds a short synthetic delivery, stores it against the user key, and analyses it like an upload.

## Storage

The default cap is 1 GB per user key. When a new video would not fit, the oldest sessions for that key are deleted (file and row). A single video larger than the cap is rejected and nothing else is deleted. The page shows how much of the cap is used.

## What a finished session contains

- `quality` — fps, size, duration, and warnings below 50 FPS or when the shorter side is below 720 px
- `preanalysis` — stump uprights, ball colour (`red`, `white`, or `unknown`), batsman on the crease, audio present
- `deliveries` — one row each, with `ball_track_id`, release, occlusion gaps, bat and batsman flags, contact, shot, and `virtual_runs`

Contact audio is a second check only. The value is `confirmed`, `not confirmed`, or exactly `no audio second confirmation` when the clip has no usable audio. Audio never creates a contact on its own.

Shots are a geometric label (`defence`, `straight drive`, `cover drive`, `cut`, `on drive`, `pull`, `no shot`). Runs assume the ball carries in a straight line at the measured exit speed for 2.0 seconds. These defaults are pending approval; see the goals file.

## Tests

```bash
pytest
```

Synthetic clips still exercise the classic colour fallback. `tests/test_real_labels.py` checks the two phone clips against `Sample/labels.json`.

## Swapping the YOLO model

YOLO is the detector on real footage. Classic colour and shape runs only when a role is missing from the class map, or when the frame is the flat synthetic pitch.

The active model is `models/detectors.json`. The shipped entry is `coco`: Ultralytics YOLO11n (`models/yolo11n.pt`) with COCO classes `person` (0) and `sports_ball` (32). Person boxes are split into batsman and bowler by where they stand. `bat` and `stumps` are not in COCO, so those two roles use the classic fallback until a model names them.

To use your own weights later, copy the file into `models/` and point the `cricket` entry at it (or add a new entry). Then either set `"active"` or export the name:

```bash
export BOWLINGER_MODEL=cricket
export BOWLINGER_MODEL_CONFIG=models/detectors.json   # optional, this is the default
python -m bowlinger
```

The `cricket` entry maps `batsman`, `bowler`, `bat`, `ball`, and `stumps` (including the class `stump- bails`). A role may name one class or a list of them. Change the numbers to match the file's `names`. No code change.

When `models/cricket.pt` is present it is selected automatically. That file is a YOLO11n fine-tune of the Roboflow Universe set [cricket-object-detection v2](https://universe.roboflow.com/jignesh-workspace/cricket-object-detection-qnjwo/dataset/2) by jignesh-workspace, license **CC BY 4.0**. The images are not in this repository. Unpack a YOLO export with:

```bash
python scripts/fetch_cricket_dataset.py export.zip
```

That writes `~/cricket_dataset` and turns polygon rows into detection boxes.

`BOWLINGER_DETECTOR=classic` forces the colour fallback. `BOWLINGER_DETECTOR=yolo` forces the configured model even on a synthetic frame. The default `auto` uses YOLO on a real camera image and classic on the synthetic pitch.

If `models/yolo11n.pt` is missing:

```bash
python scripts/download_yolo_weights.py
```

## Defaults pending approval

- Warn under 50 FPS, or when the shorter side is under 720 px
- 1 GB per user key, oldest session flushed first
- Audio confirms a video contact only inside ±0.15 s
- A ball track survives a 0.35 s occlusion, then takes a new id
- Scale from stump height 0.711 m (or 20.12 m if both stump ends are visible)
