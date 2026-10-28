# Music canvases

Approved in chat on 2026-10-28: implement without further interaction gates.

## Behaviour
- `/canvas` and exact text `canvas` render the caller's current Last.fm track, 15 seconds, in private and group chats.
- `/npcanvas`, `/npc`, `npcanvas`, `npc` render the same ordered grid as `/np`, with six seconds per available participant. Exactly one track plays at a time; transitions never overlap audio. Only the active card animates/highlights; other cards remain visible.
- Preserve the chat's theme, cover, artist/title and participant name; MP4 H.264/AAC, playable in Telegram.
- No source picker, fragment picker, extra buttons or confirmation questions. Missing/uncertain audio: explain in solo; retain the card but skip its audio turn in groups. All missing: explain instead of sending a silent movie.

## Approach
Use Last.fm artist/title (including Spotify-scrobbled songs), search YouTube and SoundCloud through yt-dlp, rank artist/title/version/duration and reject poor matches. Source audio is obtained from the matched host, never from Spotify's protected stream. Keep source attribution in the reply caption.

Select a continuous excerpt using YAMNet singing/rap probabilities, repeated audio embeddings, energy and silence penalties. On instrumental songs omit the vocal requirement. Choose near an onset and apply short edge fades within each clip. This is a heuristic, not a guarantee of detecting the chorus. Alternatives: fixed/loudest offset is cheap but often picks instrumental intros; source separation plus full transcription is too costly for this server.

## Resource and failure limits
One render job globally, bounded admission queue, per-process timeouts, subprocess termination on cancellation, one encode thread. Analyse 16 kHz mono at sparse windows; stream video frames instead of keeping them in memory. Source duration <= 10 minutes and file <= 40 MiB. Temporary files deleted after send/failure; bound Telegram file_id cache (no permanent media library). Group output is split into bounded video parts if necessary; every participant is considered in order.

## Integration
New canvas modules for resolver, excerpt analysis, render, orchestration and handlers. Reuse existing collage grid/theme drawing at reduced cell size. Add FFmpeg and small LiteRT runtime/model, no full TensorFlow/PyTorch. Tests cover matching rejection, instrumental/vocal scoring, sequential audio, missing sources, caller identity, aliases and cancellation cleanup. Network download accuracy and musical preference require representative real tracks; never claim fixture tests prove those.
