# Groupstats approved design and implementation

`/groupstats [days]`: group-only video, default seven days, maximum thirty, registered group members in stable database order. Per member use their highest-playcount track in the exact requested period. Count refers to that track, not total plays.

Each scene lasts ten seconds including transitions. Avatar square enters from left with username below. Flip around vertical axis reveals the Last.fm album cover, username transitions into artist/title, with playcount below and audio-reactive equalizer. Accent derives from avatar. Scene exits right; next enters left. Audio never overlaps. Missing avatars use initials; missing covers use a deliberate placeholder. Members with no plays or unavailable audio are skipped with explanation.

Reuse shared canvas admission, analysis, sequential YouTube/SoundCloud resolver and streaming FFmpeg encoder. Process members sequentially, clean temporary media after each member, split only for Telegram upload size. Bounded participants/time; no permanent media storage.

Implementation split: Terra renderer agent owns bot/canvas/groupstats.py; Terra handler agent owns bot/handlers/groupstats.py plus menu/help wiring; parent reviews integration and documentation. No tests or deployment requested. No PR until requested.
