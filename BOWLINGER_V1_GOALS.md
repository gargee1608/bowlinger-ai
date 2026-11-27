# BOWLINGER AI V1 – Goals File

> **Single source of truth** for V1 scope and progress.
> Status legend: `[ ]` Not started · `[/]` In progress · `[x]` Completed (only after successful testing)

**Last updated:** 2026-11-27
**Current stage:** YouTube input, a fixed stump box, pitch and role rules, training pages, and the admin history page are in the app. The phone clips still do not show a reliable ball track, so a release is not accepted unless the path moves toward the stumps or the user marks it.
**Next goal to work on:** G2. The ball in `Sample/sample_01.mp4` and `sample_02.mp4` is still too small for a trusted trajectory.

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

**In scope:** pre-video analysis & quality check, offline upload/analysis sessions, a YouTube link analysed like an upload, anonymous demo mode, a fixed stump box and an optional pitch box, role labels (batsman, bowler, fielder, wicketkeeper, bat, ball, stumps), ball release detection, ball detection & tracking, bat/batsman detection, bat-ball contact detection, shot identification, virtual run calculation, a training page, an audio training page, and a password-protected save-history page.

**Out of scope for V1:** bowling speed, line & length maps beyond the user-drawn pitch box, player stats, LBW/DRS, live streaming, multi-camera fusion (unless approved).

---

## G0 – Project Foundation
- [x] Confirm existing codebase location and audit current implementation. This repo is the V1 app: FastAPI, SQLite job queue, local video files, OpenCV and librosa. `tests/test_g0_foundation.py`.
- [x] Define input format. Uploads are mp4, mov, mkv, webm, avi or m4v. FPS and the shorter side are checked (GB). Audio is optional. The two real clips are portrait phone video from a practice net.
- [x] Collect / label a small test set of deliveries (hit, miss, edge cases). `Sample/labels.json` has 7 swings read from the frames (3 in sample_01, 4 in sample_02). The ball itself was not visible, so release is the bowling stride where it could be seen, contact is the bat coming down, and runs are filled in only for the block. No confirmed miss is in the set. `tests/test_real_labels.py`.
- [x] Set up pipeline skeleton: video + audio loading, per-delivery output structure. `bowlinger/pipeline/analyze.py`.
- [x] Define test method and pass criteria for each goal. Synthetic clips must match the generator. Real clips are recorded below and only confirm a check when the picture agrees. `pytest`.

## GA – Pre-Video Analysis (runs first on every video)
- [/] Detect stumps / wickets in the frame. Synthetic white stumps: 3 uprights, `tests/test_ga_preanalysis.py`. On `sample_01` the near yellow stick and blue stick are found (count 2; the second yellow stick and the far wooden wicket are missed). On `sample_02` the far wooden stumps are not found.
- [/] Identify ball type (e.g. red / white / tennis – list to be confirmed). Synthetic red and white pass on the classic fallback. Both real clips report `unknown`. COCO `sports_ball` does not see a cricket ball a few pixels wide. A custom `ball` class will replace that.
- [x] Detect batsman on the crease. YOLO11n `person`, split by size and place. Both real clips report the striker on the crease. `tests/test_real_labels.py`. The synthetic blue torso still uses the classic fallback.
- [x] Check whether the video has an audio track. Both real clips have AAC audio and `audio_present` is true (RMS above 0.005). A missing or silent stream is not audio. Synthetic coverage is in `tests/test_ga_preanalysis.py`.
- [x] If audio present: enable audio as second confirmation for contact (G4). The pipeline does this. On the real clips the audio check runs and returns `not confirmed` because no onset sits on a trustworthy video contact.
- [x] If no audio: run video-only mode and flag "no audio second confirmation" in results. Exact string, tested on synthetic clips with no audio stream. The two real clips both have audio, so they do not exercise this branch.
- [/] Test: correct scene/setup detection on test set, incl. videos with and without audio. Batsman and audio are confirmed. Stumps are only the near painted wicket on sample_01. Ball type is not.

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
- [/] Detect bowler and bowling arm during run-up/action. The bowler is the large YOLO person at the near end. There is no pose model for the arm. sample_02's bowler is mostly out of frame, so those deliveries have no release time.
- [/] Identify the frame where the ball leaves the hand. The ball is not resolved. On sample_01 the three labelled strides are 20.5 s, 40.05 s and 58.1 s. The detector reports 20.18 s, 39.72 s and 58.25 s, inside the 0.6 s tolerance. That is the stride, not a seen ball leaving the hand.
- [/] Start a new delivery record at release. The labelled ones are present. Extra readings are also emitted (practice swings and noise). See the table below.
- [x] Test: release frame within agreed tolerance on test set. `tests/test_real_labels.py` allows 0.6 s. The three labelled sample_01 releases pass. Synthetic release remains exact on the classic path (`tests/test_g1_release.py`).

## G2 – Ball Detection & Tracking
- [/] Detect the cricket ball per frame. Synthetic red and white balls use the classic fallback. The fine-tune's ball class has validation mAP50 0.725, but on the phone clips it only appears on a couple of frames, so the flight is not a confirmed track.
- [/] Track the ball from release toward the batsman. Works on synthetic clips. Not observed on the real clips.
- [/] Store ball position and movement across frames (trajectory). Stored for synthetic tracks. The four `sample_01` tracks are stored and are not a ball trajectory.
- [/] Maintain a single ball identity throughout one delivery. Synthetic occlusion keeps one id (`tests/test_g2_tracking.py`). Not shown on real footage.
- [/] Recover tracking when the ball is temporarily hidden (prediction / re-association). Synthetic gap on frames 8–13 keeps `ball-1` and marks those frames predicted. A gap longer than 0.35 s starts a new id. Not shown on real footage.
- [/] Test: tracking continuity and ID consistency on test set. Synthetic tests pass. Real clips do not confirm it.

## G3 – Bat & Batsman Detection
- [x] Detect the batsman. YOLO `person` at the far crease on both real clips, and the classic torso on synthetic clips.
- [/] Detect the cricket bat. COCO has no bat class, so this role is on the classic fallback list until `models/cricket.pt` is dropped in. On the phone clips `bat_detected` is set when the striker's box swings. That is not a bat box. Synthetic bat detection still passes (`tests/test_g3_bat.py`).
- [/] Track the bat during the delivery. Not implemented as a moving bat track. The synthetic bat is still, and that is enough for the synthetic contact test only.
- [/] Report bat position as the ball approaches. Reported on synthetic deliveries. Not on the real clips.
- [/] Test: bat detection/tracking accuracy near the contact zone. Synthetic only. Not upgraded.

## G4 – Bat-Ball Contact Detection
- [/] Video-based contact check (ball-bat proximity + trajectory change). Exact on synthetic clips. The four unconfirmed `sample_01` tracks have no video contact. Not a real-footage pass.
- [x] Audio-based contact check (bat-ball impact sound). Librosa onsets. When audio exists and an onset is within ±0.15 s of a video contact, the flag is `confirmed`. When audio exists and the onset does not line up, the flag is `not confirmed`. Tested on synthetic audio. Real clips have audio; their unconfirmed tracks correctly stay `not confirmed` rather than inventing a hit from sound alone.
- [x] Fuse video + audio into a hit / miss decision (audio used only when GA confirms audio is present). Audio never creates a contact by itself. A synthetic miss stays `video_detected: false`.
- [x] Output contact timestamp. All 7 labelled bat-down times match within 0.5 s (`tests/test_real_labels.py`). sample_01: 20.88 s, 40.40 s, 58.54 s. sample_02: 5.29 s, 10.00 s, 38.92 s, 66.22 s.
- [/] Track ball direction after contact. Used for shot and runs on synthetic clips. Not confirmed on real footage. COCO `sports_ball` finds nothing; frame-difference points are not a trusted trajectory.
- [/] Test: hit/miss accuracy and timestamp error on test set. Timestamp recall passes. Precision does not: sample_01 also reports contacts near 2.0, 10.0, 33.8, 50.0, 65.9, 70.0 and 80.0 s, and sample_02 near 22.5, 30.0, 50.2, 54.3 and 69.6 s. Those were not labelled shots. `tests/test_g4_contact.py` still covers the synthetic flag strings.

## G5 – Shot Identification
- [x] Define the V1 shot type list (e.g. defence, drive, cut, pull, sweep, leave/miss). Default list, pending approval: `defence`, `straight drive`, `cover drive`, `cut`, `on drive`, `pull`, and `no shot` when there is no video contact. Sweep is not in the list.
- [/] Classify shot from bat movement + post-contact ball direction. Synthetic labels in `tests/test_g5_shot.py` match the classic exit-angle rule. On the phone clips the shot name does not match `Sample/labels.json` (the block and the drives are not separated). Not marked complete.
- [/] Test: shot classification accuracy on labelled test set. The label file exists. The real-clip test checks time, not shot name, because the names do not match.

## G6 – Virtual Run Calculation
- [/] Track the ball after the shot. Synthetic post-contact points are used. Real clips do not yield a post-shot track.
- [x] Define run estimation rules (shot type, direction, speed, distance). Default, pending approval: straight-line carry at the measured exit speed for 2.0 s. Boundary 60 m. Exit speed under 6 m/s is a defence and 0 runs. Then ≥60 m lofted = 6, ≥60 m along the ground = 4, ≥42 m = 3, ≥25 m = 2, ≥12 m = 1, else 0. This is not a learned model and not a fielder simulation.
- [/] Estimate virtual runs per delivery. Synthetic checks: 0, 2, 4 and 6 (`tests/test_g6_runs.py`). Not confirmed on real footage. With no trustworthy exit speed the real clips do not get a run estimate that should be trusted. `sample_02` has no delivery. `sample_01`'s unconfirmed tracks are `no shot` and 0.
- [x] Display estimated runs for each delivery (overlay / output). The session JSON and the results screen show runs per delivery. Checked in the browser on a synthetic demo.
- [/] Test: estimated runs vs. labelled expected runs. No labelled real runs. Not upgraded.

The carry-based `virtual_runs` number above is unchanged. A separate outcome run is 1 for a hit, and 0 for a miss or a dead ball. See G4.

## GE – YouTube input
- [x] A URL field in the browser. The home page posts to `POST /api/sessions/youtube`.
- [x] The server downloads the video with yt-dlp and analyses it like an upload. The download function is in `bowlinger/youtube.py`. A live YouTube fetch was not run in this environment; the test uses a stand-in file.
- [x] The URL is not saved in a file. The session stores the video title only. `tests/test_areas_and_pages.py`.
- [x] Test: a rejected non-YouTube link, and a download that leaves no copy of the URL on disk.

## GA – Stump lock (added)
- [x] Detect and label stumps in the first 5 frames, then keep one fixed box for the whole video. Later sightings do not move it. `lock_stump_box`.
- [x] If those frames have no stump, show the first frame and let the user draw the box. That drawing is the reference. `POST /api/sessions/{id}/marks`. The phone clips did lock a box, so they did not open this fallback. The API test covers a drawn box.
- [x] Derive a larger stump area, expanded on all four sides, and track movement inside it. Both phone clips recorded movement samples.
- [x] Test: the lock ignores a later box; a missing detection asks for a drawing; both phone clips keep one fixed box. `sample_01` locked the near sticks at the bottom of the frame. `sample_02` locked a small box. One box is kept, not two wickets.

## GF – Pitch area and dead ball
- [x] The user can draw a box around the pitch. It is the area for players, the ball, the bat, and bowling events. `POST /api/sessions/{id}/marks`. A rectangle is stored as a 4-point polygon.
- [x] A ball that moves outside that box is a dead ball. A hit inside the box stays a hit. Tested with points, not with a pitch drawn on the phone clips.
- [x] If bowling events are missing, expand the pitch once and look again.
- [x] Test: a point outside the box is a dead ball; a found event does not expand the box. The phone clips had no pitch box, so nothing on them was called a dead ball.
- [x] The pitch can be an irregular polygon. Clicks add points with no limit of four, lines join them, points can be dragged or removed, Complete Area closes the shape, and Clear and Redraw starts again. The closed shape is a transparent fill. The same controls are on the session drawing panel and on `/train`. The pages were checked for those buttons. The clicks themselves were not driven in a browser.
- [x] The polygon is saved on the session and stays the fixed boundary until the user edits it. `POST /api/sessions/{id}/analyse` (the Analysis button) reruns analysis with the current stump box and that polygon. `tests/test_areas_and_pages.py`.
- [x] Point-in-polygon decides whether the ball, the bat, and players are inside. A ball point outside the polygon is a dead ball, same as the rectangle rule. Ball tracking, contact, and `virtual_runs` are not otherwise changed. An L-shaped pitch marks the outside point as a dead ball and leaves `virtual_runs` at 4.

## GG – Who is who
The cricket model classes are ball, bat, batsman, bowler, fielder, gloves, pads, stumps, and wicket-keeper. A class is used when the model has it. The rules below fill the rest.
- [x] The batsman is a person with a bat, near the locked stumps. That check runs before the ball-release flag. `sample_01` did not confirm a batsman: the locked box is the near sticks, and the striker is at the other end. `sample_02` did confirm one. The older "batsman on crease" flag is unchanged.
- [x] The bowler is the person with a bowling action. Both phone clips report a bowler. A class label without the action is not used.
- [x] A fielder has no pads and no gloves. The rule is tested. The phone clips list fielder boxes the model fired; they are not confirmed people.
- [/] The wicketkeeper is behind the stumps, by position and by gloves or the keeper class. The rule is tested on a drawn box. Neither phone clip produced a keeper.
- [x] Test: the rules on drawn boxes, and both phone clips record the roles the model returned.

## G1 – Release rule (added)
- [x] A release counts only when the ball's trajectory moves toward the stumps. `sample_01`'s three deliveries were not accepted. `sample_02` accepted some tracks; the labels still say the ball was not resolved, so those accepts are not treated as a real ball.
- [x] If the model cannot see the release, the user can mark the frame. A manual frame is stored. The outcome waits for three points.
- [x] Keep one ball identity, fill missing detections from the frames on either side, and do not decide a trajectory outcome until there are at least 3 ball points after release.
- [x] Test: a path that approaches the stumps is accepted; a path that leaves them is not; a one-point manual mark is stored but not decided. The old stride time in `release_time_s` is kept. The labelled sample_01 releases still match within 0.6 s.

## G4 – Outcome runs (added)
- [x] When a ball is delivered and the clip has audio, the audio check runs. Both phone clips have audio, and each delivery stores `audio_confirmation`.
- [x] Hit (a video contact that is not a dead ball) = 1 outcome run. Miss = 0. Dead ball = 0. On these clips every emitted delivery is a video hit, so the miss row was not seen in the phone footage. The miss and dead-ball numbers are covered by the unit test.
- [x] The existing carry-based `virtual_runs` is still calculated and still shown. `tests/test_g6_runs.py`. The labelled block on sample_01 stays 0 carry runs and is also outcome run 1, because a hit and a block are different numbers.
- [x] Test: the three outcome numbers, and both phone clips keep a hit on a video contact. Labelled contact times still match within 0.5 s. Extra contacts on sample_02 remain.

## GH – Box training page
- [x] `/train` can mark stumps, pitch, batsman, bowler, fielder, wicketkeeper, bat, and ball, plus the release frame and the contact frame.
- [x] A saved annotation replaces what the model said for that frame. It does not retrain the weights.
- [x] Annotations store the frame number and the timestamp.
- [x] Export is YOLO label files (`class x y w h`) plus the event list.
- [x] Test: a saved ball box exports as class 0. The page itself was not clicked in a browser in this run.

## GI – Audio training page
- [x] `/train/audio` asks for a waveform and a spectrogram, and plays the session video.
- [x] The user marks a timestamp as hit or miss. The mark stores the timestamp and the matching frame.
- [x] Test: the waveform endpoint returns peaks for a saved session, and an audio annotation saves. The spectrogram image and playback were not opened in a browser in this run.

## GJ – Save history
- [x] `/admin/history` lists sessions newest first, with a video URL and a link to `/s/<session id>`.
- [x] `/admin`, `/admin/history`, `/train`, and `/train/audio` ask for `BOWLINGER_ADMIN_PASSWORD` when it is set. When it is unset or empty, those pages and their APIs are open.
- [x] The password is documented in `DEPLOY.md`. An empty password leaves the pages open.
- [x] Test: a wrong password is rejected; the history row links to `/s/<id>`.

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
- G1 on real footage. The new rule rejects a release that does not move toward the stumps. sample_01's three stride times still match, and none of those ball tracks were accepted. sample_02 accepted some tracks even though the labels say the ball was not visible.
- A wicketkeeper was not found on either phone clip.
- sample_01's batsman is not "near" the locked near-stump box, so the new batsman label is no. The older crease flag is still yes.
- G2, G3, G5 and G6 accuracy on real footage. The ball, the far wooden stumps, and the bat are not reliably detected in these two phone clips. sample_02 still emits extra contacts.
- A second yellow upright on the near wicket in `sample_01` (one yellow stick is found, one is not).
- Approval of the open decisions below.

## Known Issues & Limitations

### Real clips

Both files are portrait phone video of a practice net, with audio. They are not a broadcast side-on feed. The ball at the far end is only a few pixels wide.

| Clip | FPS | Resolution | Audio | What was detected |
| --- | --- | --- | --- | --- |
| sample_01.mp4 | 30.00 (2422 frames, 80.74 s) | 478×850 | yes | Cricket YOLO model. Striker found. Near stumps found. Ball type unknown. Labelled contacts within 0.5 s and the three releases within 0.6 s. Shot name was defence for the two drives as well. Extra contacts remain. |
| sample_02.mp4 | 29.99 (2101 frames, 70.05 s) | 478×850 | yes | Cricket YOLO model. Striker found. Far wooden stumps still not counted as a wicket. Ball type unknown. The four labelled contacts match within 0.5 s. Shot names do not match drive/pull. Extra contacts remain, including practice swings. |

### Other limits
- Synthetic clips use flat colours, a frontal zoom, and a ball drawn larger than a real cricket ball. They prove the pipeline logic. They do not prove nets or match accuracy.
- The stump lock keeps one box from the first five frames. On sample_01 that is the near yellow and blue sticks, low in the portrait frame. The far wicket is not a second locked box. The expanded area is that box grown by half its size on every side. Movement inside it is a sample of frame-difference times, not a tracked person.
- A YouTube analysis was tested with a stand-in file. yt-dlp is installed, and a live YouTube download was not run here.
- The training pages save boxes and hit/miss marks. They do not train a new `.pt`.
- The pitch polygon was tested as geometry and through the session API. Placing, dragging, and deleting points was not clicked in a browser.
- `models/cricket.pt` is a YOLO11n fine-tune (8 epochs, imgsz 960, CPU) of Roboflow Universe jignesh-workspace/cricket-object-detection-qnjwo v2, CC BY 4.0. Validation: mAP50 0.688, mAP50-95 0.496. Per class mAP50: ball 0.725, bat 0.636, batsman 0.825, bowler 0.877, stumps 0.617, stump-bails 0.000. The images are not in git. The phone clips are a different look from that set, so the ball and the far bat are still mostly missed.
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
