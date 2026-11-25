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
