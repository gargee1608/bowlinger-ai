# BOWLINGER AI V1 — Goals

Last updated: 2026-11-25 (G0 tests passed)

Current stage: G0 foundation is in place. Platform sessions are next.

Next goal to work on: GB — offline analysis on a session id

> Source note: the session attachment was not present on disk (`BOWLINGER_V1_GOALS.md` / `BOWLINGER_V1_GOALS_73fe.md`). This file is the working goals document, written to match the approved V1 scope in the project brief. It is the source of truth for this repository from here on. Open decisions stay open. Defaults below are implemented so the system can run, and they are marked pending approval.

## How to use this file

Before each task: read this file, pick one goal, check the existing code, and change only what that goal needs.

After each task: run the tests for that goal, then update this file. Mark `[x]` only after the test passes. Use `[/]` when the work is partial or when a computer-vision goal has been checked only on synthetic clips. Record pending work and known issues. Update `Last updated`, `Current stage`, and `Next goal to work on`.

No features outside this scope. No second implementation of the same behaviour.

## Approved scope

V1 is a local cricket video tool.

- A person uploads a cricket video, or runs an anonymous demo with no account.
- The system checks the video before the delivery pipeline: stumps/wickets, ball type, batsman on the crease, audio presence, and a quality check of frame rate and resolution.
- Analysis is an offline background job tied to a session id. The person can leave the page and come back.
- Anonymous demo users receive a session id they can save and use to open that public session later.
- Storage is capped at 1 GB per user. When a new video would exceed the cap, the oldest videos/sessions are force-flushed.
- Per delivery, the pipeline then does: ball release, ball detection and tracking (persistent id, occlusion recovery), bat and batsman detection, bat-ball contact (video first; audio is a second confirmation only when audio exists, otherwise the delivery is flagged `no audio second confirmation`), shot identification, and a virtual run estimate shown per delivery.
- There is a minimal web UI for upload, session status, results, and retrieval by session id.

There is no labelled cricket footage in this project. Computer-vision goals are validated on synthetic clips generated in tests (a moving ball, stumps, a batsman, a bat, and an impact sound). Those goals stay `[/]` until real footage is checked, with a known-issue note that real-footage accuracy is unverified.

Suggested order, and the order this repo follows: G0, GB, GC, GD, GA, G1, G2, G3, G4, G5, G6.

## Open decisions

These are not resolved. The implementation uses the default in the right-hand column so the product can run. Change the default in `bowlinger/config.py` (or the matching environment variable) if a decision lands elsewhere.

| Decision | Default in this repo (pending approval) |
| --- | --- |
| Quality warning thresholds | Warn below 50 FPS or below 720 px vertical. A clip exactly on the threshold does not warn. |
| Storage flush order | Oldest session first, by `created_at`, for that user key only. |
| Quota identity | A user key. Anonymous users are given a generated key (`anon_…`) and can reuse it. No accounts. |
| Who can read a session | Anyone with the session UUID. Sessions are public. IDs are unguessable. |
| Audio second-confirmation window | ±0.15 s around the video contact time. |
| What "audio present" means | An audio stream whose RMS energy is above 0.005. A missing stream, or a silent stream, is treated as no audio. |
| Occlusion gap before a new ball id | 0.35 s. |
| Scale reference | Detected stump height = 0.711 m. If two stump ends are visible and far apart, the 20.12 m pitch length is used instead. No perspective correction. |
| Virtual runs | Straight-line carry at the measured post-contact speed for 2.0 s. Boundary 60 m. Under 6 m/s exit speed is a defence and 0 runs. Buckets: ≥60 m lofted = 6, ≥60 m ground = 4, ≥42 m = 3, ≥25 m = 2, ≥12 m = 1, else 0. |
| Shot names | `defence`, `straight drive`, `cover drive`, `cut`, `on drive`, `pull`, plus `no shot` when there is no video contact. Angle is measured from the bowler-ward axis, positive to image-right. |
| Detector | Classic colour and shape. COCO-style YOLO weights are not bundled: those classes do not include a stump, a bat, or a cricket ball. |
| Single file larger than the quota | Rejected. Older sessions are not deleted in that case. |

## Goals

### G0 — Foundation

- [x] Python package, FastAPI app, pinned requirements, Docker Compose, and `python -m bowlinger`
- [x] SQLite schema (users, sessions, jobs) and local data directory
- [x] Documented defaults in config, exposed read-only at `GET /api/config`
- [x] SQLite job queue: claim one job, record completion, record handler failure
- [x] Synthetic clip writer (video via ffmpeg, optional impact sound) for later tests
- [x] `GET /api/health` returns ok
- [x] Automated tests in `tests/test_g0_foundation.py` pass

### GB — Offline analysis on a session id

- [ ] Uploading a video creates a session and a queued job and returns immediately with the session id
- [ ] A background worker (or the synchronous test worker) runs the job after the response is not required to stay open
- [ ] `GET /api/sessions/{id}` shows queued, running, completed, or failed, and stores the result or the error
- [ ] A second client can read the same session id after the uploader is gone
- [ ] The web UI can upload a file and poll status
- [ ] Tests in `tests/test_gb_sessions.py` pass

### GC — Anonymous demo and public retrieval

- [ ] Upload and demo work with no account
- [ ] A missing user key is generated, returned, and stored with the session
- [ ] `POST /api/demo` builds a synthetic delivery, stores it under the quota, and enqueues analysis
- [ ] The session is readable by id with no other credential
- [ ] The UI can open a saved session id, including a direct link
- [ ] Tests in `tests/test_gc_anonymous.py` pass

### GD — 1 GB cap and oldest-first flush

- [ ] Each user key has a storage cap (default 1 GB)
- [ ] A video larger than the cap is rejected and nothing else is deleted
- [ ] When a new video would exceed the cap, oldest sessions for that user are deleted (file and row) until it fits
- [ ] Another user's sessions are left alone
- [ ] A flushed session id no longer resolves
- [ ] Usage is visible on the user endpoint and in the UI
- [ ] Tests in `tests/test_gd_quota.py` pass

### GA — Pre-video analysis and quality

- [ ] Quality report: fps, width, height, duration, warnings below the default 50 FPS / 720p thresholds
- [ ] Stumps/wickets detected on a synthetic frame (count of uprights)
- [ ] Ball type `red` or `white` from the moving ball
- [ ] Batsman on the crease, true or false
- [ ] Audio presence, true or false
- [ ] Results stored on the session by the existing job, not a second pipeline
- [/] Real-footage accuracy is unverified — do not mark this goal `[x]` on synthetic tests alone

### G1 — Ball release

- [ ] Each delivery has a release frame and a release time
- [ ] A ball that sits in the hand and then moves is released at the motion start, not at the first still frame
- [/] Checked on synthetic clips only. Real-footage accuracy is unverified.

### G2 — Ball detection and tracking

- [ ] The ball keeps one id for a delivery
- [ ] A short occlusion keeps that id, and the missing frames are marked predicted
- [ ] A gap longer than the configured maximum starts a new id
- [ ] Two deliveries in one clip become two tracks
- [/] Checked on synthetic clips only. Real-footage accuracy is unverified.

### G3 — Bat and batsman

- [ ] Batsman region detected on the synthetic crease
- [ ] Bat detected as an elongated object at the crease
- [ ] Each delivery reports whether the bat and the batsman were detected
- [/] Checked on synthetic clips only. Real-footage accuracy is unverified. Kit colours that blend into the pitch will be missed.

### G4 — Bat-ball contact

- [ ] Video contact frame from the change in ball direction beside the bat
- [ ] When audio is present and an onset falls in the confirmation window, audio confirmation is `confirmed`
- [ ] When audio is present but no onset falls in the window, audio confirmation is `not confirmed`
- [ ] When there is no usable audio, audio confirmation is exactly `no audio second confirmation`
- [/] Checked on synthetic clips only. Real-footage accuracy is unverified. Audio never creates a contact by itself.

### G5 — Shot identification

- [ ] Post-contact direction is labelled per delivery using the documented angle buckets
- [ ] A delivery with no video contact is `no shot`
- [ ] A slow exit after contact is `defence`
- [/] Checked on synthetic clips only. Real-footage accuracy is unverified. The label set is a geometric heuristic, not a trained classifier.

### G6 — Virtual runs per delivery

- [ ] Each delivery has an integer virtual run estimate from the documented distance buckets
- [ ] The estimate is in the session payload and on the results screen, per delivery
- [/] Checked on synthetic clips only. Real-footage accuracy is unverified. This is a straight-line carry model, not a fielder simulation.

## Pending work

- GB through G6 as listed above.
- Real cricket clips and a labelled check of GA and G1–G6.
- Approval of the open decisions.

## Known issues

- No labelled match footage is in the repo. Synthetic clips use flat colours, a frontal zoom, and a ball drawn larger than a real cricket ball so the classic detector has a stable signal.
- YOLO / COCO weights are not shipped. Pretrained "sports ball" and "person" classes are a poor fit for a cricket ball, stump, and bat, so V1 uses classic colour and shape on purpose.
- The run and shot models ignore swing, seam, bounce, and perspective.
