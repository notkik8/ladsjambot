"""Procedural event stickers (pure Pillow, supersampled) scattered over rendered images."""
import math
import random
from functools import lru_cache
from typing import Callable, Dict, Iterable, Optional, Tuple

from PIL import Image, ImageDraw

from bot.themes import Theme

SS = 4  # supersampling factor
_FACE = (30, 14, 40, 255)


def _canvas(px: int) -> Tuple[Image.Image, ImageDraw.ImageDraw, int]:
    s = px * SS
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im), s


def _pts(s: int, pts: Iterable[Tuple[float, float]]):
    return [(x * s, y * s) for x, y in pts]


def _snowflake(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    c, r = s / 2, s * 0.46
    w = max(3, s // 22)
    for k in range(6):
        a = k * math.pi / 3
        ex, ey = c + r * math.cos(a), c + r * math.sin(a)
        d.line([(c, c), (ex, ey)], fill=(235, 246, 255, 255), width=w)
        for f in (0.5, 0.75):
            bx, by = c + r * f * math.cos(a), c + r * f * math.sin(a)
            for da in (-0.8, 0.8):
                d.line([(bx, by), (bx + r * 0.22 * math.cos(a + da), by + r * 0.22 * math.sin(a + da))],
                       fill=(235, 246, 255, 255), width=w)
    d.ellipse([c - w * 1.4, c - w * 1.4, c + w * 1.4, c + w * 1.4], fill=(255, 255, 255, 255))
    return im


def _ornament(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    d.line([(s * 0.5, 0), (s * 0.5, s * 0.2)], fill=(230, 230, 240, 255), width=max(2, s // 40))
    d.rounded_rectangle([s * 0.42, s * 0.16, s * 0.58, s * 0.27], radius=s * 0.02, fill=(255, 214, 90, 255))
    d.ellipse([s * 0.12, s * 0.24, s * 0.88, s * 0.96], fill=(230, 50, 70, 255))
    d.arc([s * 0.2, s * 0.42, s * 0.8, s * 0.88], 20, 160, fill=(255, 214, 90, 255), width=s // 18)
    d.arc([s * 0.2, s * 0.32, s * 0.8, s * 0.78], 20, 160, fill=(255, 214, 90, 255), width=s // 18)
    d.ellipse([s * 0.24, s * 0.34, s * 0.4, s * 0.5], fill=(255, 255, 255, 150))
    return im


def _tree(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    d.rectangle([s * 0.44, s * 0.82, s * 0.56, s * 0.96], fill=(120, 76, 40, 255))
    for i, (top, half, bot) in enumerate(((0.16, 0.22, 0.45), (0.3, 0.3, 0.65), (0.46, 0.4, 0.86))):
        d.polygon(_pts(s, [(0.5, top), (0.5 + half, bot), (0.5 - half, bot)]), fill=(40, 160, 84, 255))
    for x, y, col in ((0.42, 0.5, (255, 72, 84)), (0.6, 0.64, (255, 214, 90)), (0.38, 0.76, (80, 200, 255)),
                      (0.66, 0.8, (255, 72, 84)), (0.52, 0.36, (255, 214, 90))):
        d.ellipse([s * (x - 0.035), s * (y - 0.035), s * (x + 0.035), s * (y + 0.035)], fill=col + (255,))
    star = []
    for k in range(10):
        r = 0.09 if k % 2 == 0 else 0.04
        a = -math.pi / 2 + k * math.pi / 5
        star.append((0.5 + r * math.cos(a), 0.12 + r * math.sin(a)))
    d.polygon(_pts(s, star), fill=(255, 224, 100, 255))
    return im


def _pumpkin(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    orange, dark = (255, 126, 10, 255), (220, 90, 0, 255)
    d.polygon(_pts(s, [(0.46, 0.2), (0.54, 0.2), (0.6, 0.06), (0.5, 0.1)]), fill=(70, 150, 50, 255))
    for x0, x1, col in ((0.06, 0.58, dark), (0.42, 0.94, dark), (0.2, 0.8, orange)):
        d.ellipse([s * x0, s * 0.2, s * x1, s * 0.92], fill=col)
    d.polygon(_pts(s, [(0.34, 0.42), (0.44, 0.42), (0.39, 0.54)]), fill=_FACE)
    d.polygon(_pts(s, [(0.56, 0.42), (0.66, 0.42), (0.61, 0.54)]), fill=_FACE)
    d.polygon(_pts(s, [(0.3, 0.62), (0.4, 0.7), (0.45, 0.64), (0.5, 0.72), (0.55, 0.64), (0.6, 0.7),
                       (0.7, 0.62), (0.64, 0.8), (0.36, 0.8)]), fill=_FACE)
    return im


def _bat(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    col = (28, 14, 40, 255)
    left = [(0.5, 0.36), (0.38, 0.26), (0.2, 0.24), (0.03, 0.34), (0.1, 0.4), (0.13, 0.55), (0.24, 0.47),
            (0.3, 0.62), (0.4, 0.5), (0.46, 0.66)]
    d.polygon(_pts(s, left + [(1 - x, y) for x, y in reversed(left)]), fill=col)
    d.ellipse([s * 0.44, s * 0.3, s * 0.56, s * 0.62], fill=col)
    d.polygon(_pts(s, [(0.44, 0.34), (0.45, 0.2), (0.5, 0.3), (0.55, 0.2), (0.56, 0.34)]), fill=col)
    for x in (0.465, 0.535):
        d.ellipse([s * (x - 0.014), s * 0.37, s * (x + 0.014), s * 0.4], fill=(255, 220, 60, 255))
    return im


def _ghost(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    body = (246, 244, 255, 255)
    d.ellipse([s * 0.16, s * 0.08, s * 0.84, s * 0.76], fill=body)
    d.rectangle([s * 0.16, s * 0.42, s * 0.84, s * 0.86], fill=body)
    for k in range(3):
        x0 = 0.16 + k * 0.2267
        d.ellipse([s * x0, s * 0.76, s * (x0 + 0.2267), s * 0.96], fill=body)
    for x in (0.38, 0.62):
        d.ellipse([s * (x - 0.06), s * 0.34, s * (x + 0.06), s * 0.5], fill=_FACE)
    d.ellipse([s * 0.45, s * 0.54, s * 0.55, s * 0.68], fill=_FACE)
    return im


def _pancake(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    d.ellipse([s * 0.04, s * 0.08, s * 0.96, s * 0.96], fill=(190, 110, 30, 255))
    d.ellipse([s * 0.06, s * 0.04, s * 0.94, s * 0.88], fill=(244, 176, 70, 255))
    d.ellipse([s * 0.16, s * 0.14, s * 0.84, s * 0.78], fill=(252, 200, 100, 255))
    for x, y in ((0.3, 0.3), (0.62, 0.26), (0.7, 0.55), (0.34, 0.58), (0.5, 0.45)):
        d.ellipse([s * (x - 0.035), s * (y - 0.03), s * (x + 0.035), s * (y + 0.03)], fill=(226, 148, 52, 255))
    d.rounded_rectangle([s * 0.4, s * 0.3, s * 0.62, s * 0.5], radius=s * 0.03, fill=(255, 240, 150, 255))
    d.rounded_rectangle([s * 0.4, s * 0.3, s * 0.62, s * 0.36], radius=s * 0.03, fill=(255, 252, 205, 255))
    return im


def _sun(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    c = s / 2
    for k in range(12):
        a = k * math.pi / 6
        pts = [(c + s * 0.48 * math.cos(a), c + s * 0.48 * math.sin(a)),
               (c + s * 0.3 * math.cos(a + 0.2), c + s * 0.3 * math.sin(a + 0.2)),
               (c + s * 0.3 * math.cos(a - 0.2), c + s * 0.3 * math.sin(a - 0.2))]
        d.polygon(pts, fill=(255, 196, 40, 255))
    d.ellipse([s * 0.24, s * 0.24, s * 0.76, s * 0.76], fill=(255, 214, 70, 255))
    d.ellipse([s * 0.34, s * 0.4, s * 0.4, s * 0.46], fill=(190, 100, 20, 255))
    d.ellipse([s * 0.6, s * 0.4, s * 0.66, s * 0.46], fill=(190, 100, 20, 255))
    d.arc([s * 0.38, s * 0.44, s * 0.62, s * 0.66], 20, 160, fill=(190, 100, 20, 255), width=s // 40)
    return im


def _egg(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    poly = []
    for k in range(120):
        t = k * 2 * math.pi / 120
        x = 0.5 + 0.36 * math.sin(t) * (1 - 0.18 * math.cos(t))
        y = 0.54 - 0.44 * math.cos(t)
        poly.append((x * s, y * s))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    art = Image.new("RGBA", (s, s), (255, 186, 214, 255))
    ad = ImageDraw.Draw(art)
    zig = []
    for k in range(13):
        zig.append((s * k / 12, s * (0.42 if k % 2 else 0.5)))
    ad.polygon(zig + [(s, s * 0.62), (0, s * 0.62)], fill=(150, 205, 255, 255))
    ad.rectangle([0, s * 0.7, s, s * 0.76], fill=(255, 236, 130, 255))
    for k in range(5):
        ad.ellipse([s * (0.22 + 0.14 * k) - s * 0.025, s * 0.2 - s * 0.025, s * (0.22 + 0.14 * k) + s * 0.025,
                    s * 0.2 + s * 0.025], fill=(255, 255, 255, 255))
    im.paste(art, (0, 0), mask)
    return im


def _heart(px: int) -> Image.Image:
    im, d, s = _canvas(px)
    poly = []
    for k in range(160):
        t = k * 2 * math.pi / 160
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        poly.append((s * (0.5 + x / 36), s * (0.46 - y / 36)))
    d.polygon(poly, fill=(255, 62, 108, 255))
    d.ellipse([s * 0.2, s * 0.2, s * 0.34, s * 0.3], fill=(255, 255, 255, 120))
    return im


_MAKERS: Dict[str, Callable[[int], Image.Image]] = {
    "snowflake": _snowflake, "ornament": _ornament, "tree": _tree, "pumpkin": _pumpkin, "bat": _bat,
    "ghost": _ghost, "pancake": _pancake, "sun": _sun, "egg": _egg, "heart": _heart,
}


@lru_cache(maxsize=64)
def sticker(kind: str, px: int) -> Image.Image:
    """Smooth RGBA sticker of the given pixel size."""
    px = max(16, px)
    return _MAKERS[kind](px).resize((px, px), Image.Resampling.LANCZOS)


def place(base: Image.Image, theme: Theme, kind: str, cx: float, cy: float, px: int,
          angle: float = 0.0, alpha: float = 1.0) -> None:
    """Paste one rotated sticker centred at (cx, cy) onto an RGB/RGBA image."""
    st = sticker(kind, px)
    if angle:
        st = st.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    if alpha < 1:
        st = st.copy()
        st.putalpha(st.getchannel("A").point(lambda v: int(v * alpha)))
    base.paste(st, (int(cx - st.width / 2), int(cy - st.height / 2)), st)


def scatter(base: Image.Image, theme: Theme, box: Tuple[int, int, int, int], count: int, seed: int,
            size: Tuple[int, int], alpha: float = 1.0) -> None:
    """Randomly (but deterministically) sprinkle theme stickers inside box = (x0, y0, x1, y1)."""
    if not theme.themed or count <= 0:
        return
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    for i in range(count):
        kind = theme.stickers[i % len(theme.stickers)]
        px = rnd.randint(*size)
        place(base, theme, kind, rnd.uniform(x0, x1), rnd.uniform(y0, y1), px,
              angle=rnd.uniform(-28, 28), alpha=alpha)


def snow(base: Image.Image, box: Tuple[int, int, int, int], count: int, seed: int, radius: Tuple[int, int],
         alpha: int = 150) -> None:
    """Soft round particles (snow / confetti dust)."""
    rnd = random.Random(seed)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    for _ in range(count):
        r = rnd.randint(*radius)
        x, y = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(alpha // 2, alpha)))
    base.alpha_composite(layer) if base.mode == "RGBA" else base.paste(layer, (0, 0), layer)
