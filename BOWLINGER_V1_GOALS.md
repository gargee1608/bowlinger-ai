# BOWLINGER AI V1 – Goals File

> **Single source of truth** for V1 scope and progress.
> Status legend: `[ ]` Not started · `[/]` In progress · `[x]` Completed (only after successful testing)

**Last updated:** 2026-11-25
**Current stage:** Local app runs. Quality check and audio presence are confirmed on the two real nets clips. Ball tracking, contact, shot and runs are not.
**Next goal to work on:** G1–G6 on labelled real deliveries. The two sample clips are not labelled, and the current detector does not track the ball in them.

---

## Development Workflow (mandatory for every task)

**Before starting a task**
1. Read this file.
2. Identify the relevant goal below.
3. Check existing code and current implementation.
4. Confirm what is already completed.
5. Work only on the selected goal.

**After completing a task**
1. Test the implemented feature.
2. Update this file.
3. Mark the task `[x]` only after the test passes.
4. Record pending work and known issues.
5. Report what was completed and what remains.

**Rules**
- No features outside approved V1 scope.
- No duplicate functionality.
- Do not remove working features without approval.
- Keep changes focused and minimal.
- Never mark a feature complete without testing.

---

## V1 Scope

**In scope:** pre-video analysis & quality check, offline upload/analysis sessions, anonymous demo mode, ball release detection, ball detection & tracking, bat/batsman detection, bat-ball contact detection, shot identification, virtual run calculation.

**Out of scope for V1:** bowling speed, line & length / pitch maps, fielder tracking, player stats, LBW/DRS, live streaming, multi-camera fusion (unless approved).

---

## G0 – Project Foundation
- [x] Confirm existing codebase location and audit current implementation. This repo is the V1 app: FastAPI, SQLite job queue, local video files, OpenCV and librosa. `tests/test_g0_foundation.py`.
- [x] Define input format. Uploads are mp4, mov, mkv, webm, avi or m4v. FPS and the shorter side are checked (GB). Audio is optional. The two real clips are portrait phone video from a practice net.
- [/] Collect / label a small test set of deliveries (hit, miss, edge cases). `Sample/sample_01.mp4` and `Sample/sample_02.mp4` are in the repo via Git LFS. They are not labelled delivery by delivery, so they cannot score release, contact, shot or runs.
- [x] Set up pipeline skeleton: video + audio loading, per-delivery output structure. `bowlinger/pipeline/analyze.py`.
- [x] Define test method and pass criteria for each goal. Synthetic clips must match the generator. Real clips are recorded below and only confirm a check when the picture agrees. `pytest`.

## GA – Pre-Video Analysis (runs first on every video)
- [/] Detect stumps / wickets in the frame. Synthetic white stumps: 3 uprights, `tests/test_ga_preanalysis.py`. On `sample_01` the near yellow stick and blue stick are found (count 2; the second yellow stick and the far wooden wicket are missed). On `sample_02` the far wooden stumps are not found.
- [/] Identify ball type (e.g. red / white / tennis – list to be confirmed). Synthetic red and white pass. On both real clips the ball is too small. `sample_02` reports `unknown`. `sample_01` reports `red` only because four unconfirmed tracks near the near stumps are red-tinted specks, not a ball that was seen in play.
- [/] Detect batsman on the crease. Synthetic blue torso passes, and it is absent when not drawn. Both real clips report false. The striker is a small figure in whites at the far end. The blue practice stump is not counted as a person.
- [x] Check whether the video has an audio track. Both real clips have AAC audio and `audio_present` is true (RMS above 0.005). A missing or silent stream is not audio. Synthetic coverage is in `tests/test_ga_preanalysis.py`.
- [x] If audio present: enable audio as second confirmation for contact (G4). The pipeline does this. On the real clips the audio check runs and returns `not confirmed` because no onset sits on a trustworthy video contact.
- [x] If no audio: run video-only mode and flag "no audio second confirmation" in results. Exact string, tested on synthetic clips with no audio stream. The two real clips both have audio, so they do not exercise this branch.
- [/] Test: correct scene/setup detection on test set, incl. videos with and without audio. Audio presence is confirmed on the real clips and the no-audio flag on synthetic clips. Stumps, ball type and the batsman are not confirmed on the real clips.

## GB – Video Quality & FPS Check
- [x] Define minimum required FPS and resolution for reliable ball tracking. Default, still pending approval: warn under 50 FPS, and warn when the shorter side is under 720 px. A clip exactly on the threshold does not warn. The product warns. It does not reject. See Open Decisions.
- [x] Check uploaded video FPS, resolution and quality against requirements. Both real clips are 478×850 at 30 FPS. `tests/test_ga_preanalysis.py` locks those figures.
- [x] Reject or warn the user if the video is below requirements, with the reason. Both real clips warn: frame rate about 30 is below 50 FPS, and the shorter side 478 px is below 720p. A synthetic 1280×720 clip at 50 FPS does not warn. A 640×480 clip at 25 FPS warns for both.
- [x] Test: pass/fail/warn behaviour on good and poor-quality sample videos. Covered by the synthetic cases and both real clips.

## GC – Offline Upload & Background Analysis Sessions
- [x] Upload video and create an analysis session with a unique session ID. `POST /api/sessions`. `tests/test_gb_sessions.py` (file name predates this goal id).
- [x] Save the uploaded video to storage. Under `data/videos/<user key>/`.
- [x] Run analysis as a background job (offline, not tied to the browser screen). A slow job test returns before the handler finishes.
- [x] User can leave the screen once upload completes; analysis keeps running. A second client reads the same session id.
- [x] Session status: uploaded / analysing / completed / failed. The API words are `queued` (uploaded), `running` (analysing), `completed`, and `failed`.
- [x] Results retrievable later by session ID. `GET /api/sessions/{id}` and the page `/s/{id}`.
- [x] Test: upload, close screen, return later and retrieve completed results. `tests/test_gb_sessions.py`.

## GD – Anonymous Demo Mode & Storage Limits
- [x] Anonymous session mode for demo (no login required). `POST /api/demo` and upload with no user key. `tests/test_gc_anonymous.py`.
- [x] Anon user can upload a video, have it saved and analysed under an ID only. A missing key is minted as `anon_…` and returned.
- [x] Anon user can save the session number/ID and retrieve the public session later. Anyone with the UUID can read it. The UI opens `/s/{id}`.
- [x] Storage quota of 1 GB per user. `BOWLINGER_QUOTA_BYTES` overrides it. `GET /api/users/{user_key}`.
- [x] When quota is exceeded: force flush (delete oldest videos/sessions) to free space. Oldest session for that user key only. A file larger than the cap is rejected and nothing else is deleted. `tests/test_gd_quota.py`.
- [x] Test: anon upload → retrieve by ID; quota enforcement and force flush behaviour.

## G1 – Ball Release Detection
- [/] Detect bowler and bowling arm during run-up/action. Not implemented. Release is inferred from the ball starting to move, not from the arm. The real clips do not show a reliable ball, so the arm was not added.
- [/] Identify the frame where the ball leaves the hand. Exact on synthetic clips, including a ball that is held and then moves (`tests/test_g1_release.py`). Not confirmed on either real clip.
- [/] Start a new delivery record at release. Synthetic clips do this. `sample_01` still emits four unconfirmed tracks near the near stumps (about 19.6 s, 39.1 s, 48.8 s and 57.6 s). They are specks, not labelled releases. `sample_02` emits none.
- [/] Test: release frame within agreed tolerance on test set. Tolerance on synthetic clips is exact. No labelled real tolerance exists. Not upgraded.

## G2 – Ball Detection & Tracking
- [/] Detect the cricket ball per frame. Synthetic red and white balls are detected. On the real clips the ball is a few pixels at the far end of a 478 px-wide frame. Loose red and white specks are not treated as proof of a ball.
- [/] Track the ball from release toward the batsman. Works on synthetic clips. Not observed on the real clips.
- [/] Store ball position and movement across frames (trajectory). Stored for synthetic tracks. The four `sample_01` tracks are stored and are not a ball trajectory.
- [/] Maintain a single ball identity throughout one delivery. Synthetic occlusion keeps one id (`tests/test_g2_tracking.py`). Not shown on real footage.
- [/] Recover tracking when the ball is temporarily hidden (prediction / re-association). Synthetic gap on frames 8–13 keeps `ball-1` and marks those frames predicted. A gap longer than 0.35 s starts a new id. Not shown on real footage.
- [/] Test: tracking continuity and ID consistency on test set. Synthetic tests pass. Real clips do not confirm it.

## G3 – Bat & Batsman Detection
- [/] Detect the batsman. Synthetic blue torso only. Both real strikers wear white and are small in frame. `batsman_detected` is false on both clips. That is a miss, not a confirmed absence.
- [/] Detect the cricket bat. Synthetic bat passes, and it is false when not drawn (`tests/test_g3_bat.py`). A bat is only kept when it sits near a detected wicket, so fence poles and the shed are not a bat. Neither real clip has a confirmed bat at the striker.
- [/] Track the bat during the delivery. Not implemented as a moving bat track. The synthetic bat is still, and that is enough for the synthetic contact test only.
- [/] Report bat position as the ball approaches. Reported on synthetic deliveries. Not on the real clips.
- [/] Test: bat detection/tracking accuracy near the contact zone. Synthetic only. Not upgraded.

## G4 – Bat-Ball Contact Detection
- [/] Video-based contact check (ball-bat proximity + trajectory change). Exact on synthetic clips. The four unconfirmed `sample_01` tracks have no video contact. Not a real-footage pass.
- [x] Audio-based contact check (bat-ball impact sound). Librosa onsets. When audio exists and an onset is within ±0.15 s of a video contact, the flag is `confirmed`. When audio exists and the onset does not line up, the flag is `not confirmed`. Tested on synthetic audio. Real clips have audio; their unconfirmed tracks correctly stay `not confirmed` rather than inventing a hit from sound alone.
- [x] Fuse video + audio into a hit / miss decision (audio used only when GA confirms audio is present). Audio never creates a contact by itself. A synthetic miss stays `video_detected: false`.
- [/] Output contact timestamp. Present for synthetic contacts. No confirmed real contact timestamp.
- [/] Track ball direction after contact. Used for shot and runs on synthetic clips. Not confirmed on real footage.
- [/] Test: hit/miss accuracy and timestamp error on test set. No labelled real hits or misses. Not upgraded. `tests/test_g4_contact.py` covers the synthetic cases, including the exact flag `no audio second confirmation`.

## G5 – Shot Identification
- [x] Define the V1 shot type list (e.g. defence, drive, cut, pull, sweep, leave/miss). Default list, pending approval: `defence`, `straight drive`, `cover drive`, `cut`, `on drive`, `pull`, and `no shot` when there is no video contact. Sweep is not in the list.
- [/] Classify shot from bat movement + post-contact ball direction. Classification uses the exit angle of the ball, not bat movement. Synthetic labels in `tests/test_g5_shot.py` match that rule. Real clips do not confirm a shot. The one noisy reading that remains is `no shot` because those tracks have no video contact.
- [/] Test: shot classification accuracy on labelled test set. There is no labelled real set. Not upgraded.

## G6 – Virtual Run Calculation
- [/] Track the ball after the shot. Synthetic post-contact points are used. Real clips do not yield a post-shot track.
- [x] Define run estimation rules (shot type, direction, speed, distance). Default, pending approval: straight-line carry at the measured exit speed for 2.0 s. Boundary 60 m. Exit speed under 6 m/s is a defence and 0 runs. Then ≥60 m lofted = 6, ≥60 m along the ground = 4, ≥42 m = 3, ≥25 m = 2, ≥12 m = 1, else 0. This is not a learned model and not a fielder simulation.
- [/] Estimate virtual runs per delivery. Synthetic checks: 0, 2, 4 and 6 (`tests/test_g6_runs.py`). Not confirmed on real footage. With no trustworthy exit speed the real clips do not get a run estimate that should be trusted. `sample_02` has no delivery. `sample_01`'s unconfirmed tracks are `no shot` and 0.
- [x] Display estimated runs for each delivery (overlay / output). The session JSON and the results screen show runs per delivery. Checked in the browser on a synthetic demo.
- [/] Test: estimated runs vs. labelled expected runs. No labelled real runs. Not upgraded.

---

## Completed Features
- G0 pipeline skeleton, input formats, and the test harness. The real clips are not a labelled delivery set.
- GA audio presence on both real clips, the audio second-confirmation path, and the no-audio flag on synthetic clips.
- GB quality warnings. Both real clips are warned for 30 FPS and a 478 px shorter side.
- GC offline sessions: upload, background job, leave and return, status, retrieve by id.
- GD anonymous demo, public session id, 1 GB cap, oldest-first force flush.
- G4 rule that audio only confirms a video contact and never creates one. The flag strings are tested.
- G5 shot list and G6 run rules are defined (pending approval) and the runs number is shown per delivery.
- Synthetic coverage for release, tracking through a short gap, bat and batsman on the drawn crease, contact, shot name and runs. Those goals stay `[/]` until labelled real deliveries agree.

## Pending Features
- Label the real clips delivery by delivery (release frame, hit or miss, shot, runs).
- G1 bowler and bowling-arm release. Not started.
- G1–G3, G5 and G6 accuracy on real footage. The ball, the far wooden stumps, the striker in whites, and the bat are not reliably detected in these two phone clips.
- A second yellow upright on the near wicket in `sample_01` (one yellow stick is found, one is not).
- Approval of the open decisions below.

## Known Issues & Limitations

### Real clips

Both files are portrait phone video of a practice net, with audio. They are not a broadcast side-on feed. The ball at the far end is only a few pixels wide.

| Clip | FPS | Resolution | Audio | What was detected |
| --- | --- | --- | --- | --- |
| sample_01.mp4 | 30.00 (2422 frames, 80.74 s) | 478×850 | yes | Quality warns: below 50 FPS, shorter side 478 px below 720p. Near wicket: one yellow upright and the blue upright (count 2). Second yellow upright missed. Far wooden wicket missed. Batsman on crease: no. Ball type: reported `red` from unconfirmed specks, not from a ball in play. Four unconfirmed tracks near the near stumps (release about 19.6 s, 39.1 s, 48.8 s, 57.6 s), all `no shot`, 0 runs, video contact false, audio `not confirmed`. Not a confirmed release, track, contact, shot or run. |
| sample_02.mp4 | 29.99 (2101 frames, 70.05 s) | 478×850 | yes | Quality warns: below 50 FPS, shorter side 478 px below 720p. Stumps: not detected (far wooden stumps are too small and not yellow or blue). Batsman on crease: no. Ball type: `unknown`. Deliveries: none. |

### Other limits
- Synthetic clips use flat colours, a frontal zoom, and a ball drawn larger than a real cricket ball. They prove the pipeline logic. They do not prove nets or match accuracy.
- YOLO / COCO weights are not shipped. Those classes do not include a stump, a bat, or a cricket ball. V1 uses colour and shape.
- Practice stumps in `sample_01` are yellow and blue. White-only detection counted floodlit specks, so a wicket now has to be two or three uprights seen for most of the clip. Wooden stumps on `sample_02` still fail.
- Tracks that last longer than 2.5 s, crawl, or never reach a detected wicket are dropped. That removed the long false tracks. It does not create a real ball track.
- Scale, when a wicket is found, uses stump height 0.711 m with no perspective correction. The near stumps in `sample_01` are close to the camera, so that scale would be wrong for the far end. Runs are not trusted on that clip.
- Shot and run models ignore swing, seam, bounce, fielders and bat swing. Sweep is not a V1 shot.
- Session status words in the API are `queued` and `running`. The goal text says uploaded and analysing. They are the same states.

## Open Decisions
- Shot type list for V1. Default in code: defence, straight drive, cover drive, cut, on drive, pull, no shot. Sweep is not included. Pending approval.
- Run estimation rules (rule-based vs. learned). Default is the rule-based carry above, not a learned model. Pending approval.
- Accuracy targets / pass criteria per goal. Not set. Synthetic tests must match the generator. Real clips are not marked `[x]` without a labelled agreement.
- Minimum FPS / resolution thresholds (GB). Default: warn under 50 FPS or when the shorter side is under 720 px. Warn, do not reject. Pending approval.
- Ball type list for V1 (GA). Default detector vocabulary is red, white, or unknown. Tennis ball is not a separate class. Pending approval.
- Force-flush policy: delete oldest first, and whether to warn the user before flushing (GD). Default: oldest session for that user key, no warning prompt, the UI shows bytes used. A file larger than the cap is rejected without deleting anything. Pending approval.
- Retention period for anonymous public sessions (GD). Default: kept until the 1 GB cap flushes them, or the data directory is removed. No time limit. Pending approval.
