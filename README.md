# BOWLINGER AI V1

Local cricket video analysis. Upload a clip, or run the anonymous demo. Analysis is a background job on a session id, so you can close the page and open the result later.

Each delivery reports release, ball track, bat and batsman, bat-ball contact, a shot name, and a virtual run estimate. The vision steps are checked on synthetic clips generated in the tests. Real-footage accuracy is not verified: `Sample/sample_01.mp4` and `Sample/sample_02.mp4` were not in this workspace. Status and open decisions are in [BOWLINGER_V1_GOALS.md](BOWLINGER_V1_GOALS.md).

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
docker compose up --build
```

Same port. The database and videos stay in the `bowlinger-data` volume.

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

- `quality` — fps, size, duration, and warnings below 50 FPS or below 720 px height
- `preanalysis` — stump uprights, ball colour (`red`, `white`, or `unknown`), batsman on the crease, audio present
- `deliveries` — one row each, with `ball_track_id`, release, occlusion gaps, bat and batsman flags, contact, shot, and `virtual_runs`

Contact audio is a second check only. The value is `confirmed`, `not confirmed`, or exactly `no audio second confirmation` when the clip has no usable audio. Audio never creates a contact on its own.

Shots are a geometric label (`defence`, `straight drive`, `cover drive`, `cut`, `on drive`, `pull`, `no shot`). Runs assume the ball carries in a straight line at the measured exit speed for 2.0 seconds. These defaults are pending approval; see the goals file.

## Tests

```bash
pytest
```

Computer-vision checks render a synthetic clip (pitch, stumps, batsman, bat, moving ball, optional impact sound) and run the same pipeline as an upload. They do not measure accuracy on real match footage. The real-clip test skips while `Sample/sample_01.mp4` and `Sample/sample_02.mp4` are absent.

## Defaults pending approval

- Warn under 50 FPS or under 720 px height
- 1 GB per user key, oldest session flushed first
- Audio confirms a video contact only inside ±0.15 s
- A ball track survives a 0.35 s occlusion, then takes a new id
- Scale from stump height 0.711 m (or 20.12 m if both stump ends are visible)
