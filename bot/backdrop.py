"""Generated backgrounds for themes that are not a flat colour: aurora glass, synthwave dusk, riso paper, deco black."""
import random
from typing import Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from bot.themes import RGB, Theme

SMALL = 4  # smooth backdrops are drawn at 1/SMALL size and scaled up


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _gradient(w: int, h: int, stops: Sequence[Tuple[float, RGB]]) -> Image.Image:
    """Vertical multi-stop gradient."""
    img = Image.new("RGB", (w, h), stops[0][1])
    d = ImageDraw.Draw(img)
    for y in range(h):
        p = y / max(1, h - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p <= p1:
                d.line([(0, y), (w, y)], fill=mix(c0, c1, (p - p0) / max(p1 - p0, 1e-6)))
                break
        else:
            d.line([(0, y), (w, y)], fill=stops[-1][1])
    return img


def _aurora(theme: Theme, w: int, h: int, pal: Sequence[RGB]) -> Image.Image:
    sw, sh = max(1, w // SMALL), max(1, h // SMALL)
    base = Image.new("RGB", (sw, sh), theme.bg)
    glow = Image.new("RGB", (sw, sh), theme.bg)
    d = ImageDraw.Draw(glow)
    step = int(sw * 0.62)
    r = int(sw * 0.46)
    for i, y in enumerate(range(int(sw * 0.12), sh + step, step)):
        for j, x in enumerate((int(sw * 0.08), int(sw * 0.95))):
            col = pal[(i * 2 + j) % len(pal)]
            yy = y + (int(sw * 0.3) if j else 0)
            d.ellipse([x - r, yy - r, x + r, yy + r], fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(sw * 0.16))
    out = Image.blend(base, glow, 0.5)
    return out.resize((w, h), Image.Resampling.BICUBIC)


def _dusk(theme: Theme, w: int, h: int, pal: Sequence[RGB]) -> Image.Image:
    sw, sh = max(1, w // SMALL), max(1, h // SMALL)
    sky = _gradient(sw, sh, [
        (0.0, mix(theme.bg, (0, 0, 0), 0.35)),
        (0.55, theme.bg),
        (1.0, mix(theme.bg, pal[0], 0.28)),
    ])
    glow = Image.new("RGB", (sw, sh), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([-sw * 0.2, sh - sw * 0.5, sw * 1.2, sh + sw * 0.5], fill=mix(theme.bg, pal[0], 0.55))
    glow = glow.filter(ImageFilter.GaussianBlur(sw * 0.22))
    out = ImageChops.screen(sky, glow).resize((w, h), Image.Resampling.BICUBIC)
    rnd = random.Random(w + h)
    d = ImageDraw.Draw(out)
    for _ in range(int(w * h / 55000)):  # sparse stars
        x, y = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        r = rnd.choice((1, 1, 2, 3))
        d.ellipse([x - r, y - r, x + r, y + r], fill=mix(theme.bg, (255, 235, 250), rnd.uniform(0.25, 0.8)))
    return out


def _paper(theme: Theme, w: int, h: int) -> Image.Image:
    base = Image.new("RGB", (w, h), theme.bg)
    grain = Image.effect_noise((w, h), 7).convert("RGB")
    return ImageChops.add(base, grain, 1.0, -128)


def _luxe(theme: Theme, w: int, h: int, pal: Sequence[RGB], page: bool) -> Image.Image:
    sw, sh = max(1, w // SMALL), max(1, h // SMALL)
    base = Image.new("RGB", (sw, sh), theme.bg)
    glow = Image.new("RGB", (sw, sh), theme.bg)
    ImageDraw.Draw(glow).ellipse([sw * 0.1, -sw * 0.45, sw * 0.9, sw * 0.35], fill=mix(theme.bg, pal[0], 0.38))
    glow = glow.filter(ImageFilter.GaussianBlur(sw * 0.14))
    out = Image.blend(base, glow, 0.55).resize((w, h), Image.Resampling.BICUBIC)
    if page:  # double hairline page frame
        d = ImageDraw.Draw(out)
        gold = mix(theme.bg, pal[0], 0.7)
        o, i = int(w * 0.014), int(w * 0.022)
        d.rectangle([o, o, w - o - 1, h - o - 1], outline=gold, width=max(2, w // 540))
        d.rectangle([i, i, w - i - 1, h - i - 1], outline=mix(theme.bg, pal[0], 0.35), width=1)
    return out


def render(theme: Theme, w: int, h: int, pal: Sequence[RGB], page: bool = False) -> Optional[Image.Image]:
    """Backdrop for a theme, or None when it uses the legacy flat / glow background."""
    kind = theme.backdrop
    if not kind:
        return None
    pal = list(pal) or list(theme.palette)
    if kind == "aurora":
        return _aurora(theme, w, h, pal)
    if kind == "dusk":
        return _dusk(theme, w, h, pal)
    if kind == "paper":
        return _paper(theme, w, h)
    if kind == "luxe":
        return _luxe(theme, w, h, pal, page)
    return None
