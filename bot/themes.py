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
    #                      glass (frosted) | neon (glowing outline) | clay (puffy, soft shadow) | riso (blue ink + colour offset)
    #                      deco (gold double frame, cut corners)
    hero: str = "mosaic"  # mosaic (cover wall) | band (flat colour block) | plain (text only)
    #                      glass (blurred wall + floating covers) | sun (striped sun + grid) | blob (pastel + tilted covers)
    #                      halftone (two-ink dot print) | deco (centred sunburst)
    rank: str = "pill"  # pill (round badge) | plain (bare number) | mono (zero-padded "01") | roman (I, II, III)
    glow: bool = True  # soft colour blobs on the background
    backdrop: str = ""  # generated background: aurora | dusk | paper | luxe ("" -> flat / glow)
    bar_blocks: bool = False  # bars are split into stacked blocks
    # --- structure (collage) ---
    banner: str = "gradient"  # gradient | solid (strip in bg colour) | accent (strip in accent colour) | frost (blurred glass strip)
    frame: Optional[RGB] = None  # card border colour (None -> faint glass border)
    frame_w: int = 2
    hard_shadow: bool = False
    inset: int = 10
    edge: str = ""  # card / cover finish: glass | neon | clay | riso | deco ("" -> plain frame)
    card_radius: int = 0  # collage card corner radius at 800px cells (0 -> small default)
    chamfer: float = 0.0  # cut-corner size as a fraction of the card (art deco)
    shadow_col: Optional[RGB] = None  # offset shadow colour for hard_shadow (None -> frame colour)
    soft_shadow: bool = False  # blurred drop shadow under collage cards
    dots: bool = False  # halftone dots fading out of the banner strip
    artist_tone: str = ""  # artist line colour on solid banners: "" (accent) | muted


THEMES = {
    t.key: t
    for t in (
        Theme(
            "default", "Постер", "🎵", "яркий постер: коллаж обложек, цветные плашки", "Last.fm",
            bg=(11, 9, 20), card=(27, 23, 46), line=(52, 46, 80), muted=(178, 174, 200), ink=(255, 255, 255),
            palette=(),
        ),
        Theme(
            "glass", "Аврора", "🔮", "матовое стекло на северном сиянии, пастельное свечение", "aurora",
            bg=(14, 10, 34), card=(34, 28, 68), line=(96, 88, 150), muted=(196, 190, 228), ink=(250, 248, 255),
            palette=((167, 139, 250), (94, 234, 212), (249, 168, 212), (252, 211, 77)),
            radius=1.5, panel="glass", hero="glass", rank="pill", glow=False, backdrop="aurora",
            banner="frost", frame=(255, 255, 255), frame_w=2, inset=18, edge="glass", card_radius=44,
        ),
        Theme(
            "sunset", "Синтвейв", "🌇", "неоновый закат: полосатое солнце, сетка, свечение", "sunset",
            bg=(24, 8, 46), card=(40, 14, 74), line=(104, 44, 150), muted=(196, 156, 236), ink=(255, 240, 250),
            palette=((255, 64, 160), (255, 150, 50), (50, 230, 255), (170, 110, 255)),
            radius=0.55, panel="neon", hero="sun", rank="mono", glow=False, backdrop="dusk",
            bar_blocks=False, banner="gradient", frame=None, frame_w=3, inset=22, edge="neon", card_radius=16,
        ),
        Theme(
            "candy", "Зефир", "🍡", "пастель, пухлые карточки, мягкие тени", "candy",
            bg=(253, 242, 236), card=(255, 255, 255), line=(240, 212, 206), muted=(122, 100, 112), ink=(58, 40, 66),
            palette=((255, 171, 150), (140, 224, 190), (196, 170, 235), (140, 200, 250)),
            radius=1.8, panel="clay", hero="blob", rank="pill", glow=True,
            banner="solid", frame=(255, 255, 255), frame_w=0, inset=22, edge="clay", card_radius=56,
            soft_shadow=True, artist_tone="muted",
        ),
        Theme(
            "riso", "Ризо", "🖨", "печать двумя красками: розовый и синий, полутон, зерно", "riso",
            bg=(244, 238, 226), card=(252, 249, 242), line=(0, 120, 191), muted=(88, 92, 136), ink=(20, 28, 96),
            palette=((255, 72, 176), (255, 214, 0), (0, 196, 190), (255, 112, 64)),
            radius=0.35, panel="riso", hero="halftone", rank="plain", glow=False, backdrop="paper",
            banner="accent", frame=(0, 120, 191), frame_w=5, hard_shadow=True, inset=24, edge="riso",
            card_radius=6, shadow_col=(255, 72, 176), dots=True,
        ),
        Theme(
            "luxe", "Люкс", "✨", "арт-деко: чёрное с золотой линией, римские цифры", "luxe",
            bg=(12, 10, 8), card=(24, 20, 14), line=(104, 86, 44), muted=(168, 154, 124), ink=(244, 234, 212),
            palette=((214, 174, 64), (240, 214, 140), (190, 138, 66), (222, 205, 170)),
            radius=0.0, panel="deco", hero="deco", rank="roman", glow=False, backdrop="luxe",
            banner="solid", frame=(214, 174, 64), frame_w=3, inset=26, edge="deco", chamfer=0.07,
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

ORDER = ["default", "glass", "sunset", "candy", "riso", "luxe", "brutal", "terminal", "minimal"]

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
