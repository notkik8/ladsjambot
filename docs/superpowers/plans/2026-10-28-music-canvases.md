# Music Canvases Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Execute continuously under the user's approved design.

**Goal:** Automatic solo 15-second and sequential group six-second music canvases.
**Architecture:** A single admitted job resolves tracks, analyses audio in bounded windows, streams themed frames to FFmpeg, sends video, then removes job files. External processes are owned by the job.
**Tech Stack:** aiogram, Pillow, yt-dlp, FFmpeg, NumPy, LiteRT/YAMNet.
**Spec:** ../specs/2026-10-28-music-canvases-design.md

## Global Constraints
No follow-up interaction. Solo 15 s; group 6 s per participant, no overlapping audio. Retain all cards; skip missing audio turns. One job at a time; bounded queue and subprocess timeouts. No permanent media storage.

## Review Focus
Wrong remixes/covers: reject version mismatches (resolver tests).
Instrumental and silence: no false vocal requirement, silence rejected (analysis tests).
Missing one/all group tracks: retain geometry, skip segments/report all missing (service tests).
Cancellation and timeout: kill process and clean workspace (process tests).
Large groups: split sequential parts, never silently drop participants (render/service tests).

### Task 1: Resolve and analyse
Files: bot/canvas/{process,resolver,analysis}.py, scripts/install_canvas_model.py, tests/test_canvas_audio.py.
- [ ] Add failing tests for candidate matching, dangerous versions, silence and vocal/repetition preference.
- [ ] Implement `rank_candidate(artist,title,candidate,duration=None)`, `resolve_audio(...)`, `choose_excerpt(features,seconds)`, `analyse_audio(...)`.
- [ ] Verify model provenance/hash, sparse inference and bounded resource use.

### Task 2: Render sequential canvas
Files: bot/canvas/render.py, tests/test_canvas_render.py.
- [ ] Add a real encode test with distinct synthetic tones per participant; assert duration and no overlapping tone at each segment centre.
- [ ] Reuse collage drawing; generate one frame at a time with active card and audio-driven bars.
- [ ] Encode each segment and concatenate compatible streams; edge fades only, no crossfade.

### Task 3: Integrate handlers and lifecycle
Files: bot/canvas/service.py, bot/handlers/canvas.py, main.py, config.py, requirements.txt, Dockerfile, .env.example, README.md, tests/test_canvas_handlers.py.
- [ ] Test exact aliases, caller selection, missing tracks, bounded admission, cache and cleanup.
- [ ] Wire shared service with shutdown, theme, status message and video sending. Add dependencies and setup instructions.
- [ ] Run suite, generated media QA, whole-branch review, fix significant findings and push feature branch to user's fork.
