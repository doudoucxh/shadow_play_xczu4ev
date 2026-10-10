# YOLOv8n Pose9 candidate — 2026-09-22

## CURRENT LIVE STATE UPDATE: FOLLOW version for responsiveness

User reports STABLE feels too slow. Active service is now `shadow-yolo-follow`, running
`/tmp/board_follow.py` with `/tmp/pose_responsive.py`; STABLE-v2 is stopped and retained.
Banner is `FOLLOW`. Same weights, 180-degree input, split capture and display pipeline.

Responsive mode preserves person association, missing-evidence suppression and extreme
jump rejection. During sustained motion or a confirmed position change, it uses the current
measurement instead of a trailing three-sample median. Arm response tau is 15 ms during
movement, body 25 ms; a 100 ms fast-response hold avoids slowing prematurely at the endpoint.
At rest, lighter median filtering uses tau 80 ms for arms and 120 ms for body, versus the
previous slow path at 200 ms. Deadband is reduced, and extreme arm jump gating starts at
180 px instead of 120 px. This intentionally trades some static stability for response.

20 test methods pass. Synthetic 50 px wrist step is within 6 px after two observations
at 28.6 Hz; constant-motion lag is less than 40% of the prior filter in the test fixture.
This is filter response only, NOT measured sensor-to-screen latency. Alternating-quantum
noise and a gross transient outlier tests still pass. Real action acceptance is pending.
180-frame preflight completed successfully, restored original display, ~28.6 FPS in an
empty scene with normal DMA statuses. Follow live logs for positive-scene performance.

Stop/restore: `sudo systemctl stop shadow-yolo-follow`. No SD/autostart changes were made.

## CURRENT LIVE STATE UPDATE: STABLE v2 addresses skeleton jitter

Active service is now **shadow-yolo-stable-v2**, running `/tmp/board_stable.py` with
`/tmp/pose_stability.py`. Older PIPE/FAST/STABLE services are stopped. Banner is `STABLE`.
No original model, xmodel, SD or autostart file was modified.

Evidence: actual xmodel output keypoint fix-points are 5 at stride 8, 4 at stride 16,
3 at stride 32. After 384 letterbox decode back to 720p, coordinate quantization steps
are approximately 1.67, 6.67, 26.67 pixels respectively. Saved detections contain the
coarse stride-32 lattice. Previous renderer drew raw per-frame points with no tracking
or temporal filter. Quantization and missing temporal filtering are confirmed issues;
the full share of jitter caused by scene motion or bad predictions is not established.

User was asked to stand still, but `jitter_trace.json` has detections in only 23 of 200
frames, with possible movement and later no detections. Do NOT present this as a complete
stationary benchmark. Replaying 169 valid consecutive joint transitions reduced mean
frame step from 29.50 to 10.38 px, p95 from 84.33 to 35.79 px. This is smoothing evidence,
not improved geometric accuracy or a controlled static-jitter result.

Postprocessing added:
- Associate the selected person by box overlap rather than choosing the highest score
  independently every frame. This is NOT appearance-based re-identification.
- Causal 3-sample median plus adaptive low-pass/deadband; larger sustained changes use
  a faster response with a short fast-response hold.
- Hide an unconfirmed >120 px joint jump; a consistent following observation can confirm
  it. Missing/low-confidence evidence is not rendered as a fabricated skeleton.
- Reset on loss/reacquisition and long gaps; preserve the nine keypoint IDs.

Filtering changes the displayed coordinates intentionally; model input/raw decode parity
still applies upstream. Motion response and user-perceived jitter need live acceptance.
It cannot recover sub-quantum information or correct persistent inaccurate wrist predictions.

16 test methods pass (constant/noisy poses, motion step, transient outlier, person score
order change, missing evidence, plus previous pipeline/input/decode tests). Native A53
replay measured ~2.22 ms mean, ~2.55 ms p95 on positive updates after replacing tiny NumPy
operations with scalar math; initial implementation ~6.7 ms was superseded.
250-frame short test exited 0 and restored display (mostly empty scene, ~28.6 FPS).
Latest live log is saved in `stability_live.log`; do not infer positive-scene performance
from empty-scene-only samples.

Stop with `sudo systemctl stop shadow-yolo-stable-v2` to restore original pure video.
Current camera, 180-degree orientation, DPU weights, split copy and three-stage display
pipeline remain unchanged. Reboot returns to unchanged SD pure-video baseline.

## CURRENT LIVE STATE UPDATE: PIPE version addressing visible stutter

User reported visible stutter despite ~20 FPS in FAST. Read-only index timing confirmed
capture ~28.5 FPS with ~35 ms intervals, display ~20.3 FPS with 33/50/66/82 ms intervals.
No capture/display DMA error was observed. Average FPS alone was insufficient.

Active service is now **shadow-yolo-pipeline**, running `/tmp/board_pipeline.py`.
Previous FAST and initial test services are stopped. Dependencies added:
`/tmp/pipeline_input.py`, `/tmp/display_queue.py`. Screen banner includes `PIPE`.
The original FAST modules are retained as fallback; no SD/autostart changes occurred.

Changes:
- Copy camera frame in two disjoint halves concurrently, approximately 16 ms vs 26 ms
  for one copy thread. CPU-buffer tests verify exact bytes and independent ownership.
- Accept at most one writer advance within a <30 ms copy, since the verified fixed
  camera period is >34 ms and the source is two writer advances away from being reused.
  The timing bound now begins BEFORE the first writer read; a second writer advance,
  long read, error, or stale frame is rejected. This assumption is specific to current
  720p timing and MUST be revalidated if sensor frame rate is changed.
- Three bounded stages: capture/rotation, inference/drawing, independent HDMI submission.
  Each rendered skeleton stays paired with the exact frame used for its inference;
  no old-pose/new-image mixing or motion extrapolation was added.
- FPS is counted from completed display-buffer switches, separate from inference FPS.
  Render sequence must increase; one-slot queues bound latency and record overwrites.

The intermediate three-stage version without parallel copy reached ~25 FPS but still
had ~99 ms intervals; it was not accepted as a fix. With parallel copy, a 500-inference
frame test completed successfully, steady output ~28.6 FPS, zero rejected captures and
zero display drops; initial warm-up overwrites stopped increasing after initialization.
The test exited 0 and restored original display registers.

Independent six-second timing after continuous deployment observed capture=172 and
display=172 changes (~28.66 FPS), display max interval 49.64 ms, p95 49.52 ms, no observed
66–82 ms stalls. Max polling gap was 11.71 ms, so these are software-observed buffer
switch intervals, not optical scanout or a formal hard real-time guarantee.
Some 33/50 ms cadence variation remains with the current capture and HDMI timings.
See `cadence_validation.json` for full before/after intervals, parity and live reports.

Eleven unit test methods pass, including exact block copy, safe-snapshot bounds,
render generation ordering, quantization and decoder equivalence. First positive live
detection checks input and decode parity against the reference.
User-perceived smoothness and action accuracy still require feedback.

To stop/restore pure video: `sudo systemctl stop shadow-yolo-pipeline`.
Do not concurrently start older display owners. Restart still boots unchanged pure video.

## CURRENT LIVE STATE UPDATE: optimized FAST test running

Supersedes the service/PID described in the earlier sections below.
`shadow-yolo-fast.service` is active, running `/tmp/board_fast.py`, PID 823 at verification.
The original `shadow-yolo-test` is stopped; it is retained locally for rollback.
`board_fast.py` keeps the tested independent HDMI buffers and normal-stop restoration,
with an additional `/tmp/optimized_input.py` dependency.

Measured baseline stages: capture ~42 ms, rotation ~8 ms, preprocessing ~23 ms,
DPU ~14.8 ms, decode ~3.8 ms, drawing ~2.5 ms, HDMI copy/switch ~10–12 ms.
Optimizations actually deployed:
- Exact lookup-table input quantization via OpenCV, avoiding NCHW float round trips.
- Separate camera copy/rotation thread overlapping DPU/preprocessing/display.
- One-slot latest-frame queue; older queued frames are dropped rather than accumulating
  latency. A frame and its own inferred skeleton are always rendered together.
- Reject copies that cross writer indices or exceed 30 ms, reject stale queued frames,
  propagate camera errors and join the producer before unmapping capture memory.

300-frame bounded test completed successfully and restored the original display;
steady empty-scene display/inference throughput was approximately 22.2 FPS.
Continuous test with people in view reports approximately 20–22 FPS (old version ~9.5).
All sampled DMA statuses remained 0x11000. Evidence and parity status are saved in
`optimization_validation.json`. DPU time under concurrent capture is approximately 15 ms.
This is processing/display update throughput, not a claim of 30/60 FPS or latency measured
from sensor exposure. `frame_age_ms` starts after the capture-memory copy completes.

Input parity unit tests cover 18 image/fix-point combinations. Eight unit test methods
pass, including rotation, 48 synthetic sparse-decoder comparisons, stale-frame/error
propagation and snapshot rejection. First positive live detection also checks exact
input parity and original-vs-sparse decoded boxes/scores/keypoints on the same DPU result.

The native aligned-copy experiment was slower (read ~51 ms versus NumPy ~26 ms), so
`libframe_copy.so` is NOT used by the deployed optimized program. Direct resizing from
device memory remains prohibited after the earlier SIGBUS diagnostic.

Stop safely with `sudo systemctl stop shadow-yolo-fast`; normal termination restores
the original shared-ring video. Do not start another display owner until it exits.
No SD/autostart or FPGA bitstream changes were made. Reboot returns to pure video.

## CURRENT LIVE STATE: HDMI board test running

User requested direct deployment for on-board testing. `board_test.py` is running as
transient `shadow-yolo-test.service` (PID 759 at verification), with input/display upright
rotation 180, DPU inference, sparse decode and HDMI skeleton rendering.
Boot ID remains 862b59f6-b8e7-446d-bc5a-5880519846a4.
Observed first 101 frames: approximately 9.5 complete displayed inference frames/s after
startup; DPU approximately 14.8 ms; sampled video/capture/pose DMA SRs all 0x11000.
This rate is not yet optimized. User visual acceptance is pending.

Display now reads **0x71000000, 0x712A3000, 0x71546000**, parked mode, MM2S Genlock off.
Camera capture remains the original circular ring at 0x70000000. CPU inference and rendering
operate on the same copied frame, and only inactive display buffers are written. Both the
image and points are upright here, so no inverse coordinate mapping is applied on this path.

Eight-frame preflight exited 0 and printed ORIGINAL_VIDEO_REGISTERS_RESTORED. The subsequent
six-second original-video validation passed: capture 172/display 171 updates, no overlap,
no backward/repeated generations, all three SRs 0x11000. Thus normal-stop rollback was tested.
The live test does not establish long-term stability or action accuracy.

Stop with `sudo systemctl stop shadow-yolo-test`; SIGTERM executes the tested display
restore path. Do not invoke `shadow-video-init` while this test owns the display. A hard
kill does not guarantee software cleanup. Power cycling loads unchanged pure-video SD.
No SD file, original model weight, permanent runtime or autostart service was changed.
Temporary board files: `/tmp/yolo-board-test.py`, `/tmp/orientation.py`, `/tmp/fast_decode.py`.
Runtime dependencies and model remain in `/opt/shadow/yolo_pose9`.

The statements below about HDMI not being implemented apply to earlier diagnostics and
the separate `runtime.py` candidate; `board_test.py` is the new reversible HDMI integration.

## Latest: software rotation verified after camera reconnection

User confirmed the physical installation is correct and requested software input rotation
of 180 degrees. This is now the default in candidate `runtime.py` (`--input-rotation 180`).
Rotation is applied to a CPU-owned frame BEFORE the unchanged 384x384 letterbox/RGB
preprocessing. Keypoint IDs and confidences remain unchanged. Raw-camera rendering uses
`x_camera = width - 1 - x_upright`, `y_camera = height - 1 - y_upright`.
JSON includes both coordinate spaces and the rotation setting. HDMI activation is explicitly
blocked in this candidate until shared-ring overlay is separately validated.

New boot ID: 862b59f6-b8e7-446d-bc5a-5880519846a4. Video checks before and after the
24-frame rotation test PASS: approximately 28.5 buffer updates/s, all DMA SRs 0x11000,
no sampled writer overlap or backward/repeated frame generations.
All 24 frames detected a person. Mean DPU time 14.833 ms; diagnostic full-loop mean
143.77 ms including reference decode, parity checking and full-frame rotation.
All 24 actual DPU sparse/reference decode comparisons passed with positive detections.
This does NOT establish keypoint accuracy or sustained performance.

`rotation180_preview.jpg` was retrieved and visually inspected: the person is upright,
but their head is outside the image and the predicted head point falls on the arm.
User was asked to step back for full upper-body framing. Pose accuracy remains unaccepted.
`rotation180_results.json` stores all 24 frame outputs. Three orientation unit tests and
the 48 synthetic decoder comparisons pass. Model weights and pure-video SD remain unchanged.
Board runtime and test files are under `/tmp` and are lost on reboot; this is NOT an
installed/autostart model deployment. The older interruption notes below are historical.

## Scope and current state

User explicitly selected YOLOv8n Pose9, superseding the older dual-V2 deployment choice.
This directory contains isolated, bounded headless diagnostics and an optional optimized
decoder. No installed runtime, training weight, SD boot image, or model service was replaced.
The accepted pure-video SD files remain unchanged in `../video_boot_candidate/sd_candidate`.
Do NOT enable the old `shadow-yolo-pose` launcher: its `--hdmi` path assumes a separate display
ring at 0x71000000, whereas the accepted baseline uses a shared 0x70000000 Genlock ring.

## Verified on the board

- COM3, DPUCZDX8G_ISA1_B4096, 100 MHz, fingerprint 0x101000056010407.
- `/opt/shadow/yolo_pose9/model/yolo_pose9_b4096.xmodel` SHA256:
  f01805e51f118ebb371f83de3a5c335a2fbf4fe81c4593a3fde14d565ffcb8e6.
- Model loads and runs; nine finite raw output tensors with the expected dimensions.
- DPU execution approximately 14.8 ms (not end-to-end FPS).
- Original headless loop: mean 139.48 ms, approximately 7.17 processing iterations/s.
  Capture 52.58 ms, preprocessing 12.90 ms, model wrapper 36.97 ms including DPU,
  decode 37.03 ms. See `profile_initial.log`.
- Some frames detected a person. Saved `camera_input.jpg` is upside down with the
  person only partially framed. Live accuracy has NOT been accepted.
- `fast_decode.py` passes 48 synthetic reference comparisons (24 seeds x 2 thresholds).
  Two actual DPU output comparisons also passed, but those two frames had no detections.
  Original runtime's nine host tests passed unchanged.
- Sparse INT8 decode about 1.64 ms in an empty scene. Candidate end-to-end mean still
  138.48 ms due capture waiting and preprocessing; no overall speedup is claimed.
  See `benchmark_initial.log`. Rotation 0/180 alternated for diagnosis only.

## Interruption and recovery required

Direct OpenCV resize from uncached `/dev/mem` triggered SIGBUS. Do NOT deploy
`resize_probe.py` or reuse that direct-read method. This diagnostic made no register writes.
Use a safe CPU-owned copy or a separately tested aligned native reader before resizing.

Subsequent video check found capture stopped (capture SR 0x15190, pose SR 0x1d090).
Baseline `/usr/bin/shadow-video-init` was attempted once: sensor ID 0x5640 was readable,
but capture frames timed out (exit 1). Current live video is NOT verified recovered.

The user then explicitly confirmed accidentally disconnecting the camera during these
tests. Therefore capture failure cannot be attributed to DPU load from this evidence.
User instructed to power off, reconnect securely, then cold boot the unchanged pure-video SD.
Await confirmation of smooth video before further inference testing.

## Next

1. Confirm safe camera reconnection and fresh pure-video boot; re-run read-only video check.
2. Confirm physical orientation or explicit software rotation choice; require full upper body
   in frame. Preserve image-to-display coordinate mapping if software rotation is used.
3. Run a bounded headless test with video counters monitored during the workload and
   reference parity on positive detections. Verify actual input colors and pose accuracy.
4. Improve coherent capture and preprocessing; include DMA errors, freshness and timeout
   guards. Do not conflate DPU-only timing with camera/HDMI/pose update rates.
5. Integrate overlay using explicit buffer ownership and a reversible display transition;
   validate visually before preparing a separate SD model candidate.

`benchmark.py`, `profile.py`, `probe.py` are diagnostics, not production/autostart programs.
Original `VdmaFullFrame` capture polling is still used by them and needs further review.
