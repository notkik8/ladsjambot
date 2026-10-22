"""Visual styles for rendered images: each one changes structure (corners, cards, hero, bars), not just colours."""
from dataclasses import dataclass
from typing import Optional, Tuple

RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    key: str
    title: str
    emoji: str
    blurb: str  # one-line description shown in /themes
    footer: str  # shown in the image footer next to the brand
    bg: RGB
    card: RGB
    line: RGB
    muted: RGB
    ink: RGB
    palette: Tuple[RGB, ...]  # 4 accent colours; empty -> derived from cover art
    # --- structure (infographics) ---
    radius: float = 1.0  # multiplier for every corner radius (0 = square)
    panel: str = "fill"  # fill | hard (thick border + offset shadow) | outline | none (hairlines only)
    hero: str = "mosaic"  # mosaic (cover wall) | band (flat colour block) | plain (text only)
    rank: str = "pill"  # pill (round badge) | plain (bare number) | mono (zero-padded "01")
    glow: bool = True  # soft colour blobs on the background
    bar_blocks: bool = False  # bars are split into stacked blocks
    # --- structure (collage) ---
    banner: str = "gradient"  # gradient | solid (strip in bg colour) | accent (strip in accent colour)
    frame: Optional[RGB] = None  # card border colour (None -> faint glass border)
    frame_w: int = 2
    hard_shadow: bool = False
    inset: int = 10


THEMES = {
    t.key: t
    for t in (
        Theme(
            "default", "Постер", "🎵", "яркий постер: коллаж обложек, цветные плашки", "Last.fm",
            bg=(11, 9, 20), card=(27, 23, 46), line=(52, 46, 80), muted=(178, 174, 200), ink=(255, 255, 255),
            palette=(),
        ),
        Theme(
            "brutal", "Брутализм", "🟨", "бумага, толстые чёрные рамки, жёсткие тени", "BRUTAL",
            bg=(242, 236, 222), card=(255, 255, 255), line=(20, 20, 20), muted=(84, 80, 72), ink=(16, 16, 16),
            palette=((255, 213, 0), (255, 92, 138), (60, 200, 255), (130, 230, 90)),
            radius=0.0, panel="hard", hero="band", rank="plain", glow=False, bar_blocks=False,
            banner="accent", frame=(16, 16, 16), frame_w=8, hard_shadow=True, inset=26,
        ),
        Theme(
            "terminal", "Терминал", "💻", "чёрный экран, зелёный текст, квадратные рамки", "ladsjam@lastfm:~$",
            bg=(4, 10, 6), card=(8, 22, 12), line=(30, 110, 56), muted=(88, 170, 112), ink=(150, 255, 170),
            palette=((60, 255, 110), (255, 190, 40), (70, 220, 255), (255, 90, 90)),
            radius=0.0, panel="outline", hero="plain", rank="mono", glow=False, bar_blocks=True,
            banner="solid", frame=(60, 255, 110), frame_w=3, inset=14,
        ),
        Theme(
            "minimal", "Минимал", "⬜", "светлая типографика, тонкие линии, без карточек", "Last.fm",
            bg=(247, 246, 243), card=(247, 246, 243), line=(206, 203, 196), muted=(128, 124, 116),
            ink=(22, 22, 24),
            palette=((226, 48, 62), (22, 22, 24), (40, 96, 224), (210, 150, 20)),
            radius=0.0, panel="none", hero="plain", rank="plain", glow=False,
            banner="solid", frame=None, frame_w=0, inset=44,
        ),
    )
}

ORDER = ["default", "brutal", "terminal", "minimal"]

DEFAULT = THEMES["default"]


def resolve(key: Optional[str]) -> Theme:
    """Unknown keys (e.g. retired seasonal themes) fall back to the default style."""
    return THEMES.get(key or "default", DEFAULT)


async def for_chat(db, chat_id: int) -> Theme:
    """Theme chosen for a chat (falls back to default if the lookup fails)."""
    try:
        return resolve(await db.get_chat_theme(chat_id))
    except Exception:
        return DEFAULT
