# BOWLINGER AI V1 — Goals

Last updated: 2026-11-25 (synthetic pipeline tests passed; real sample clips were not on disk)

Current stage: The local app runs the full V1 path on synthetic clips. Vision goals stay partial until real footage is checked.

Next goal to work on: Re-run GA and G1–G6 on `Sample/sample_01.mp4` and `Sample/sample_02.mp4` once those files are in the repo. Do not mark those goals `[x]` from synthetic clips alone.

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

- [x] Uploading a video creates a session and a queued job and returns immediately with the session id
- [x] A background worker (or the synchronous test worker) runs the job after the response is not required to stay open
- [x] `GET /api/sessions/{id}` shows queued, running, completed, or failed, and stores the result or the error
- [x] A second client can read the same session id after the uploader is gone
- [x] The web UI can upload a file and poll status
- [x] Tests in `tests/test_gb_sessions.py` pass

### GC — Anonymous demo and public retrieval

- [x] Upload and demo work with no account
- [x] A missing user key is generated, returned, and stored with the session
- [x] `POST /api/demo` builds a synthetic delivery, stores it under the quota, and enqueues analysis
- [x] The session is readable by id with no other credential
- [x] The UI can open a saved session id, including a direct link
- [x] Tests in `tests/test_gc_anonymous.py` pass

### GD — 1 GB cap and oldest-first flush

- [x] Each user key has a storage cap (default 1 GB)
- [x] A video larger than the cap is rejected and nothing else is deleted
- [x] When a new video would exceed the cap, oldest sessions for that user are deleted (file and row) until it fits
- [x] Another user's sessions are left alone
- [x] A flushed session id no longer resolves
- [x] Usage is visible on the user endpoint and in the UI
- [x] Tests in `tests/test_gd_quota.py` pass

### GA — Pre-video analysis and quality

- [x] Quality report: fps, width, height, duration, warnings below the default 50 FPS / 720p thresholds. Tested in `tests/test_ga_preanalysis.py` (metadata, not a vision claim).
- [/] Stumps/wickets on a synthetic frame (3 uprights). Real-footage accuracy is unverified.
- [/] Ball type `red` or `white` from the moving ball. Real-footage accuracy is unverified.
- [/] Batsman on the crease, true or false. Real-footage accuracy is unverified.
- [x] Audio presence from an audio stream whose RMS is above 0.005. A missing or silent stream is not audio. Not measured on the missing sample clips.
- [x] Results stored on the session by the existing job, not a second pipeline.
- [/] Real-footage accuracy is unverified. `tests/test_ga_preanalysis.py` skips `Sample/sample_01.mp4` and `Sample/sample_02.mp4` because those files were not in the workspace.

### G1 — Ball release

- [/] Each delivery has a release frame and a release time. Exact on the synthetic clips in `tests/test_g1_release.py`. Real-footage accuracy is unverified.
- [/] A ball that sits in the hand and then moves is released at the motion start, not at the first still frame. Real-footage accuracy is unverified.

### G2 — Ball detection and tracking

- [/] The ball keeps one id for a delivery. Real-footage accuracy is unverified.
- [/] A short occlusion keeps that id, and the missing frames are marked predicted. Tested with frames 8–13 hidden. Real-footage accuracy is unverified.
- [/] A gap longer than the configured maximum (0.35 s) starts a new id. Two deliveries become `ball-1` and `ball-2` in `tests/test_g2_tracking.py`. Real-footage accuracy is unverified.

### G3 — Bat and batsman

- [/] Batsman region detected on the synthetic crease, and absent when it is not drawn. Real-footage accuracy is unverified.
- [/] Bat detected as an elongated object at the crease. Real-footage accuracy is unverified. Kit colours that blend into the pitch will be missed.
- [/] Each delivery reports `bat_detected` and `batsman_detected`. See `tests/test_g3_bat.py`.

### G4 — Bat-ball contact

- [/] Video contact frame from the change in ball direction beside the bat. Exact on synthetic clips. Real-footage accuracy is unverified.
- [x] When audio is present and an onset falls in the ±0.15 s window, audio confirmation is `confirmed`.
- [x] When audio is present but no onset falls in the window, audio confirmation is `not confirmed`.
- [x] When there is no usable audio, audio confirmation is exactly `no audio second confirmation`.
- [/] Audio never creates a contact by itself. A miss stays `video_detected: false`. Real-footage contact accuracy is unverified. See `tests/test_g4_contact.py`.

### G5 — Shot identification

- [/] Post-contact direction is labelled per delivery using the documented angle buckets. Synthetic labels covered: defence, straight drive, cover drive, cut, on drive, pull. Real-footage accuracy is unverified.
- [/] A delivery with no video contact is `no shot`.
- [/] A slow exit after contact is `defence`.
- [/] The label set is a geometric heuristic, not a trained classifier. See `tests/test_g5_shot.py`.

### G6 — Virtual runs per delivery

- [/] Each delivery has an integer virtual run estimate from the documented distance buckets. Synthetic checks: 0 (defence and no shot), 2 (straight drive), 4 (ground shot at 40 m/s), 6 (lofted). Real-footage accuracy is unverified.
- [x] The estimate is in the session payload and on the results screen, per delivery (columns Release, Contact, Audio check, Shot, Runs).
- [/] This is a straight-line carry for 2.0 s, not a fielder simulation. See `tests/test_g6_runs.py`.

## Pending work

- Put `Sample/sample_01.mp4` and `Sample/sample_02.mp4` in `Sample/` and re-run GA and G1–G6. Record FPS, resolution, audio, and what the detectors actually returned. Do not treat the synthetic passes as real-footage accuracy.
- Approval of the open decisions.

## Known issues

- `Sample/sample_01.mp4` and `Sample/sample_02.mp4` were named in a follow-up. The upload was not saved into this workspace, so the files are not in the repo. Nothing below was measured from them.

| Clip | FPS | Resolution | Audio | Findings |
| --- | --- | --- | --- | --- |
| sample_01.mp4 | not available — file missing | not available | not available | not analysed |
| sample_02.mp4 | not available — file missing | not available | not available | not analysed |

- No labelled match footage is in the repo. Synthetic clips use flat colours, a frontal zoom, and a ball drawn larger than a real cricket ball (about 14 px across at 1 cm per pixel) so the classic detector has a stable signal. H.264 colour shift is enough to break a tight circularity test; the ball threshold is 0.42 for that reason.
- One stump upright is partly hidden by the bat in the synthetic scene, so its measured height is short. Scale uses the median upright height (0.711 m). Perspective is not corrected.
- YOLO / COCO weights are not shipped. Pretrained "sports ball" and "person" classes are a poor fit for a cricket ball, stump, and bat, so V1 uses classic colour and shape on purpose.
- The run and shot models ignore swing, seam, bounce, and fielders. A white ball can grow a red compression fringe; detections that overlap a white ball are kept as white.
- Git LFS is configured for `Sample/*.mp4` so the real clips can be added without storing the bytes as normal git objects.
