# BOWLINGER AI V1

Local cricket video analysis. Upload a clip, or run the anonymous demo. Analysis is a background job on a session id, so the page can be closed and opened again. Results are one row per delivery: release, ball track, bat-ball contact, shot, and a virtual run estimate.

The approved scope and the status of each goal are in [BOWLINGER_V1_GOALS.md](BOWLINGER_V1_GOALS.md).

## Requirements

- Python 3.11+
- ffmpeg on `PATH` (used to write and probe clips)
- Docker, only if you use Compose

## Run with Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m bowlinger
```

The app listens on port **8741** (`http://127.0.0.1:8741`). Videos and the SQLite database go in `./data`.

## Run with Docker Compose

```bash
docker compose up --build
```

Same port. The database and videos stay in the `bowlinger-data` volume.

## Upload a video

Open `http://127.0.0.1:8741`, choose a clip, and start analysis. The page polls until the session is `completed` or `failed`.

```bash
curl -s -F "video=@clip.mp4" -F "user_key=coach_1" http://127.0.0.1:8741/api/sessions
curl -s http://127.0.0.1:8741/api/sessions/SESSION_ID
```

The upload call returns a `session_id`. You can close the page and fetch that URL later. A direct page for that session is `http://127.0.0.1:8741/s/SESSION_ID`.

Leave `user_key` out and the response includes a new anonymous key. Send that key on later uploads to keep the same 1 GB budget.

## Anonymous demo

```bash
curl -s -X POST http://127.0.0.1:8741/api/demo
curl -s http://127.0.0.1:8741/api/users/USER_KEY
```

The demo builds a short synthetic delivery, stores it against the user key, and analyses it like an upload. Storage defaults to 1 GB per key. When a new video does not fit, the oldest session for that key is deleted. A single video larger than the cap is rejected.

## Tests

## Tests

```bash
pytest
```

Computer-vision checks use synthetic clips generated during the test run. They do not measure accuracy on real match footage.

## Defaults pending approval

These are the values the code ships with. They are listed as open decisions in the goals file.

- Warn when a video is under 50 FPS or under 720 px tall
- 1 GB per user key, oldest session flushed first
- Audio can confirm a video contact only inside ±0.15 s, and only when the clip actually has audio
