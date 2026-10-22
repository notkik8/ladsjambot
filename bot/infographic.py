"""
Pillow renderers for stats images - phone-first.

Design: loud, colourful "poster" look. Full-bleed cover mosaic hero, heavy Montserrat type,
big numbers, per-image palette taken from the covers, glow blobs behind everything.
Logical width is 1080 (text sizes are chosen so it stays readable at ~390pt phone width).
"""
import io
import math
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

from bot import backdrop, fonts
from bot.backdrop import mix
from bot.collage import _dominant
from bot.stats import ListeningStats
from bot.themes import DEFAULT, Theme

K = 1.5  # render scale (keeps width+height under Telegram's 10000px photo limit)
W = 1080
PAD = 48

DEFAULT_PALETTE = [(255, 61, 129), (255, 214, 10), (0, 229, 255), (150, 100, 255)]

Row = Tuple[str, str, int]  # label, sublabel, value

WHITE = (255, 255, 255)
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]


def _lum(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _open(cover: Optional[bytes]) -> Optional[Image.Image]:
    if not cover:
        return None
    try:
        with Image.open(io.BytesIO(cover)) as im:
            im = im.convert("RGB")
        m = min(im.size)
        return im.crop(((im.width - m) // 2, (im.height - m) // 2, (im.width + m) // 2, (im.height + m) // 2))
    except Exception:
        return None


def _palette(covers: Sequence[Optional[bytes]], theme: Theme = DEFAULT) -> List[Tuple[int, int, int]]:
    if theme.palette:
        return list(theme.palette)
    cols: List[Tuple[int, int, int]] = []
    for c in covers:
        im = _open(c)
        if not im:
            continue
        col = _dominant(im)
        if all(sum(abs(a - b) for a, b in zip(col, o)) > 140 for o in cols):
            cols.append(col)
        if len(cols) == 4:
            break
    for d in DEFAULT_PALETTE:
        if len(cols) >= 4:
            break
        cols.append(d)
    return cols


class Sheet:
    """Logical-coordinate drawing surface (all args in 1080-wide units)."""

    def __init__(self, height: int, palette: Sequence[Tuple[int, int, int]], theme: Theme = DEFAULT):
        self.h = height
        self.t = theme
        self.pal = list(palette)
        self.img = self._background(height)
        self.d = ImageDraw.Draw(self.img)

    def _background(self, height: int) -> Image.Image:
        w, h = int(W * K), int(height * K)
        generated = backdrop.render(self.t, w, h, self.pal, page=True)
        if generated is not None:
            return generated
        base = Image.new("RGB", (w, h), self.t.bg)
        if not self.t.glow:
            return base
        glow = Image.new("RGB", (w, h), self.t.bg)
        gd = ImageDraw.Draw(glow)
        step = int(1000 * K)
        for i, y in enumerate(range(int(500 * K), h + step, step)):
            col = self.pal[i % len(self.pal)]
            x = int((0.1 if i % 2 else 0.9) * w)
            r = int(520 * K)
            gd.ellipse([x - r, y - r, x + r, y + r], fill=col)
        glow = glow.filter(ImageFilter.GaussianBlur(int(230 * K)))
        return Image.blend(base, glow, 0.30)

    # primitives -----------------------------------------------------------
    def _b(self, x0, y0, x1, y1):
        return [int(x0 * K), int(y0 * K), int(x1 * K) - 1, int(y1 * K) - 1]

    def rect(self, x0, y0, x1, y1, fill=None):
        self.d.rectangle(self._b(x0, y0, x1, y1), fill=fill)

    def rrect(self, x0, y0, x1, y1, r, fill=None, outline=None, width=2):
        self.d.rounded_rectangle(self._b(x0, y0, x1, y1), radius=int(r * K * self.t.radius), fill=fill,
                                 outline=outline, width=int(width * K))

    def on(self, col) -> Tuple[int, int, int]:
        """Readable text colour for a given fill."""
        lum = _lum(col)
        if lum > 140 and self.t.panel in ("clay", "riso"):
            return self.t.ink
        return (12, 12, 16) if lum > 140 else (250, 250, 250)

    def fg(self, col) -> Tuple[int, int, int]:
        """Accent colour for text; on light themes bright accents (yellow) fall back to ink for contrast."""
        lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        return self.t.ink if lum(self.t.bg) > 140 and lum(col) > 120 else col

    # layered effects ------------------------------------------------------
    def composite(self, x0, y0, x1, y1, pad, paint, blur=0.0, base=(0, 0, 0)):
        """Alpha-composite an RGBA layer onto the region; paint(draw, px) draws with px(x0, y0, x1, y1) -> local pixels."""
        bx0, by0 = max(0, int((x0 - pad) * K)), max(0, int((y0 - pad) * K))
        bx1, by1 = min(self.img.width, int((x1 + pad) * K)), min(self.img.height, int((y1 + pad) * K))
        if bx1 <= bx0 or by1 <= by0:
            return

        def px(a, b, c, d):
            r = self._b(a, b, c, d)
            return [r[0] - bx0, r[1] - by0, r[2] - bx0, r[3] - by0]

        layer = Image.new("RGBA", (bx1 - bx0, by1 - by0), tuple(base) + (0,))
        paint(ImageDraw.Draw(layer), px)
        if blur:
            layer = layer.filter(ImageFilter.GaussianBlur(blur * K))
        region = self.img.crop((bx0, by0, bx1, by1)).convert("RGBA")
        self.img.paste(Image.alpha_composite(region, layer).convert("RGB"), (bx0, by0))
        self.d = ImageDraw.Draw(self.img)

    def glow(self, x0, y0, x1, y1, r, col, strength=150, spread=14, blur=8):
        """Neon halo around a rounded box."""
        rad = int(r * K * self.t.radius)
        self.composite(
            x0, y0, x1, y1, spread * 2,
            lambda d, px: d.rounded_rectangle(px(x0 - 2, y0 - 2, x1 + 2, y1 + 2), radius=rad, outline=tuple(col) + (strength,),
                                              width=int(spread * K / 2)),
            blur=blur, base=col,
        )

    def soft_shadow(self, x0, y0, x1, y1, r, dy=10, alpha=70, blur=10, col=None):
        rad = int(r * K * self.t.radius)
        col = col or mix(self.t.line, self.t.ink, 0.45)
        self.composite(
            x0, y0, x1, y1, blur * 3,
            lambda d, px: d.rounded_rectangle(px(x0, y0 + dy, x1, y1 + dy), radius=rad, fill=tuple(col) + (alpha,)),
            blur=blur, base=col,
        )

    @staticmethod
    def cut(x0, y0, x1, y1, c):
        """Octagon with chamfered corners (art deco)."""
        return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]

    def poly(self, pts, fill=None, outline=None, width=2):
        scaled = [(int(x * K), int(y * K)) for x, y in pts]
        if fill:
            self.d.polygon(scaled, fill=fill)
        if outline:
            self.d.line(scaled + [scaled[0]], fill=outline, width=max(1, int(width * K)), joint="curve")

    def chip(self, x0, y0, x1, y1, r, col):
        """Solid accent block (badge / KPI); hard style gets a thick outline + offset shadow."""
        st = self.t.panel
        if st == "hard":
            self.rect(x0 + 7, y0 + 7, x1 + 7, y1 + 7, self.t.line)
            self.rrect(x0, y0, x1, y1, r, fill=col, outline=self.t.line, width=4)
        elif st == "glass":
            self.rrect(x0, y0, x1, y1, r, fill=col, outline=mix(col, WHITE, 0.55), width=2)
        elif st == "neon":
            self.glow(x0, y0, x1, y1, r, col, strength=170, spread=10, blur=7)
            self.rrect(x0, y0, x1, y1, r, fill=col)
        elif st == "clay":
            self.soft_shadow(x0, y0, x1, y1, r, dy=8, alpha=60, blur=8)
            self.rrect(x0, y0, x1, y1, r, fill=col, outline=mix(col, WHITE, 0.55), width=3)
        elif st == "riso":
            self.rect(x0 + 6, y0 + 6, x1 + 6, y1 + 6, self.t.line)
            self.rrect(x0, y0, x1, y1, r, fill=col, outline=self.t.ink, width=3)
        elif st == "deco":
            c = min(12, (y1 - y0) / 4)
            self.poly(self.cut(x0, y0, x1, y1, c), fill=col)
            self.poly(self.cut(x0 + 5, y0 + 5, x1 - 5, y1 - 5, max(c - 4, 2)), outline=mix(col, (0, 0, 0), 0.4), width=1.2)
        else:
            self.rrect(x0, y0, x1, y1, r, fill=col)

    def panel(self, x0, y0, x1, y1, r, accent=None):
        """Container surface whose look depends on the theme's panel style."""
        st = self.t.panel
        if st == "fill":
            self.rrect(x0, y0, x1, y1, r, fill=self.t.card)
        elif st == "hard":
            self.rect(x0 + 8, y0 + 8, x1 + 8, y1 + 8, self.t.line)
            self.rrect(x0, y0, x1, y1, r, fill=self.t.card, outline=self.t.line, width=4)
        elif st == "outline":
            self.rrect(x0, y0, x1, y1, r, fill=self.t.card, outline=accent or self.t.line, width=2)
        elif st == "glass":
            rad = int(r * K * self.t.radius)

            def paint(d, px):
                box = px(x0, y0, x1, y1)
                d.rounded_rectangle(box, radius=rad, fill=(255, 255, 255, 24), outline=(255, 255, 255, 78), width=int(1.6 * K))
                inset = min(rad, int((y1 - y0) * K / 2)) * 0.8 + 6 * K
                d.line([(box[0] + inset, box[1] + 3 * K), (box[2] - inset, box[1] + 3 * K)], fill=(255, 255, 255, 110),
                       width=max(1, int(1.5 * K)))

            self.composite(x0, y0, x1, y1, 0, paint)
        elif st == "neon":
            col = accent or self.t.line
            self.rrect(x0, y0, x1, y1, r, fill=self.t.card)
            self.glow(x0, y0, x1, y1, r, col, strength=120, spread=12, blur=7)
            self.rrect(x0, y0, x1, y1, r, outline=col, width=3)
        elif st == "clay":
            col = accent or self.t.line
            self.soft_shadow(x0, y0, x1, y1, r, dy=9, alpha=64, blur=11)
            self.rrect(x0, y0, x1, y1, r, fill=self.t.card, outline=col, width=4)
            self.rrect(x0 + 8, y0 + 8, x1 - 8, y1 - 8, max(r - 8, 0), outline=mix(col, WHITE, 0.7), width=2)
        elif st == "riso":
            self.rrect(x0 + 7, y0 + 7, x1 + 7, y1 + 7, r, fill=accent or self.pal[0])
            self.rrect(x0, y0, x1, y1, r, fill=self.t.card, outline=self.t.line, width=3)
        elif st == "deco":
            c = min(16, (y1 - y0) / 4)
            gold = accent or self.pal[0]
            self.poly(self.cut(x0, y0, x1, y1, c), fill=self.t.card, outline=mix(self.t.bg, gold, 0.85), width=2)
            self.poly(self.cut(x0 + 6, y0 + 6, x1 - 6, y1 - 6, max(c - 5, 3)), outline=mix(self.t.bg, gold, 0.38), width=1)
        else:
            self.rect(x0, y1 - 2, x1, y1, self.t.line)

    def paste(self, im: Image.Image, x, y, size=None, radius=0):
        if size:
            im = im.resize((int(size * K), int(size * K)), Image.Resampling.LANCZOS)
        im = im.convert("RGB")
        radius = radius * self.t.radius
        if radius:
            m = Image.new("L", (im.width * 2, im.height * 2), 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, m.width - 1, m.height - 1], radius=int(radius * K * 2), fill=255)
            self.img.paste(im, (int(x * K), int(y * K)), m.resize(im.size, Image.Resampling.LANCZOS))
        else:
            self.img.paste(im, (int(x * K), int(y * K)))
        self.d = ImageDraw.Draw(self.img)

    def edge_under(self, x, y, size, col):
        """Finish drawn behind a square cover (album grid)."""
        e = self.t.edge
        if e == "clay":
            self.soft_shadow(x, y, x + size, y + size, 32, dy=12, alpha=70, blur=14)
            self.rrect(x - 8, y - 8, x + size + 8, y + size + 8, 38, fill=WHITE)
        elif e == "riso":
            self.rect(x + 10, y + 10, x + size + 10, y + size + 10, col)
        elif e == "glass":
            self.soft_shadow(x, y, x + size, y + size, 32, dy=14, alpha=110, blur=16, col=(0, 0, 0))

    def edge_over(self, x, y, size, col):
        e = self.t.edge
        if e == "glass":
            self.rrect(x, y, x + size, y + size, 32, outline=mix(self.t.bg, WHITE, 0.6), width=3)
        elif e == "neon":
            self.glow(x, y, x + size, y + size, 32, col, strength=160, spread=12, blur=8)
            self.rrect(x, y, x + size, y + size, 32, outline=col, width=4)
        elif e == "riso":
            self.rrect(x, y, x + size, y + size, 32, outline=self.t.line, width=4)
        elif e == "deco":
            c = size * 0.07
            for sx, sy in ((x, y), (x + size, y), (x, y + size), (x + size, y + size)):  # cut the corners
                dx, dy = (1 if sx == x else -1), (1 if sy == y else -1)
                self.poly([(sx, sy), (sx + dx * c, sy), (sx, sy + dy * c)], fill=self.t.bg)
            self.poly(self.cut(x, y, x + size, y + size, c), outline=col, width=3)
            self.poly(self.cut(x + 12, y + 12, x + size - 12, y + size - 12, c - 6), outline=mix(self.t.bg, col, 0.45), width=1.2)

    # text -----------------------------------------------------------------
    def measure(self, s: str, size: float, weight=fonts.BOLD) -> float:
        return fonts.font(max(8, int(size * K)), weight).getlength(s) / K

    def text(self, x, y, s, size, fill=None, weight=fonts.BOLD, align="l", max_w=None, stroke=None) -> float:
        """Draw text with vertical centre at y. Returns drawn width (logical)."""
        s = str(s)
        fill = fill or self.t.ink
        if max_w and self.measure(s, size, weight) > max_w:
            while s and self.measure(s + "…", size, weight) > max_w:
                s = s[:-1]
            s = s.rstrip() + "…"
        w = self.measure(s, size, weight)
        if align == "r":
            x -= w
        elif align == "m":
            x -= w / 2
        extra = {"stroke_width": int(stroke[0] * K), "stroke_fill": stroke[1]} if stroke else {}
        self.d.text((x * K, y * K), s, font=fonts.font(max(8, int(size * K)), weight), fill=fill, anchor="lm", **extra)
        return w

    def spaced(self, x, y, s, size, fill=None, weight=fonts.BOLD, track=0.0, align="m", max_w=None) -> float:
        """Letter-spaced text (centred by default); shrinks to fit max_w."""
        fill = fill or self.t.ink
        while True:
            f = fonts.font(max(8, int(size * K)), weight)
            adv = [f.getlength(ch) / K + track for ch in s]
            total = sum(adv) - track
            if not max_w or total <= max_w or size <= 24:
                break
            size -= 2
        if align == "m":
            x -= total / 2
        elif align == "r":
            x -= total
        for ch, a in zip(s, adv):
            self.d.text((x * K, y * K), ch, font=f, fill=fill, anchor="lm")
            x += a
        return total

    def label(self, x, y, s, fill=None, align="l", size=24):
        return self.text(x, y, s.upper(), size, fill or self.t.muted, fonts.SEMIBOLD, align)

    def bar(self, x0, y0, x1, y1, r, col):
        """Horizontal or vertical bar; terminal-style themes cut it into blocks."""
        if not self.t.bar_blocks:
            st = self.t.panel
            if st == "hard":
                self.rrect(x0, y0, x1, y1, r, fill=col, outline=self.t.line, width=3)
            elif st == "neon":  # stepped halo, cheap enough for dozens of bars
                halo = ((3, 0.16), (1.5, 0.36)) if min(x1 - x0, y1 - y0) < 14 else ((7, 0.16), (3.5, 0.36))
                for grow, t in halo:
                    self.rrect(x0 - grow, y0 - grow, x1 + grow, y1 + grow, r + grow, fill=mix(self.t.card, col, t))
                self.rrect(x0, y0, x1, y1, r, fill=col)
            elif st == "clay":
                self.rrect(x0, y0, x1, y1, 999, fill=col)
            elif st == "riso":
                if min(x1 - x0, y1 - y0) < 14:
                    self.rect(x0 + 3, y0 + 3, x1 + 3, y1 + 3, self.t.line)
                else:
                    self.rrect(x0 + 4, y0 + 4, x1 + 4, y1 + 4, r, outline=self.t.line, width=3)
                self.rrect(x0, y0, x1, y1, r, fill=col)
            else:
                self.rrect(x0, y0, x1, y1, r, fill=col)
            return
        if (y1 - y0) >= (x1 - x0):  # vertical: stack blocks upward
            step = 14
            y = y1
            while y - step + 3 >= y0:
                self.rect(x0, y - step + 3, x1, y, col)
                y -= step
            if y > y0 + 2:
                self.rect(x0, y0, x1, y, col)
        else:
            step = 14
            x = x0
            while x + step - 3 <= x1:
                self.rect(x, y0, x + step - 3, y1, col)
                x += step

    def export(self, quality=92) -> io.BytesIO:
        buf = io.BytesIO()
        self.img.save(buf, format="JPEG", quality=quality, subsampling=0, optimize=True)
        buf.seek(0)
        return buf


# ---- shared blocks ---------------------------------------------------------
def _hero_h(theme: Theme, h: int) -> int:
    """Hero height per style (idempotent: feeding the result back in returns the same value)."""
    kind = theme.hero
    if kind == "band":
        return max(h, 400)
    if kind == "plain":
        return 250
    if kind == "sun":
        return max(h, 340)
    if kind == "halftone":
        return max(h, 380)
    if kind == "deco":
        return 330
    return h


def _mosaic(sh: Sheet, covers: Sequence[Optional[bytes]], hw: int, hh: int) -> Image.Image:
    """Cover wall (or colour blobs when there is no artwork) at pixel size hw x hh."""
    imgs = [i for i in (_open(c) for c in covers) if i]
    hero = Image.new("RGB", (hw, hh), sh.t.card)
    if imgs:
        cols = 4 if len(imgs) >= 8 else 3 if len(imgs) >= 4 else 2
        tile = math.ceil(hw / cols)
        rows = math.ceil(hh / tile) + 1
        for i in range(cols * rows):
            t = imgs[i % len(imgs)].resize((tile, tile), Image.Resampling.LANCZOS)
            hero.paste(t, ((i % cols) * tile, (i // cols) * tile))
        return ImageEnhance.Color(hero).enhance(1.25)
    d = ImageDraw.Draw(hero)
    for i, col in enumerate(sh.pal):
        cx, cy, r = int(hw * (0.15 + 0.25 * i)), int(hh * (0.3 + 0.35 * (i % 2))), int(hh * 0.55)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    return hero.filter(ImageFilter.GaussianBlur(int(60 * K)))


def _hero(sh: Sheet, covers: Sequence[Optional[bytes]], title: str, subtitle: str, tag: str, h: int = 520) -> int:
    """Top block: cover-mosaic wall, flat colour band or plain text, depending on the theme."""
    h = _hero_h(sh.t, h)
    special = {"plain": lambda: _hero_plain(sh, title, subtitle, tag, h),
               "band": lambda: _hero_band(sh, covers, title, subtitle, tag, h),
               "glass": lambda: _hero_glass(sh, covers, title, subtitle, tag, h),
               "sun": lambda: _hero_sun(sh, title, subtitle, tag, h),
               "blob": lambda: _hero_blob(sh, covers, title, subtitle, tag, h),
               "halftone": lambda: _hero_halftone(sh, covers, title, subtitle, tag, h),
               "deco": lambda: _hero_deco(sh, title, subtitle, tag, h)}
    if sh.t.hero in special:
        return special[sh.t.hero]()
    hw, hh = int(W * K), int(h * K)
    hero = _mosaic(sh, covers, hw, hh)
    grad = Image.new("RGBA", (hw, hh), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(hh):
        p = y / hh
        gd.line([(0, y), (hw, y)], fill=sh.t.bg + (int(250 * p ** 1.1 + 40 * (1 - p)),))
    hero = Image.alpha_composite(hero.convert("RGBA"), grad).convert("RGB")
    sh.img.paste(hero, (0, 0))
    sh.d = ImageDraw.Draw(sh.img)

    # tag chip
    acc = sh.pal[0]
    tw = sh.measure(tag.upper(), 26, fonts.EXTRABOLD)
    sh.rrect(PAD, 44, PAD + tw + 48, 100, 28, fill=acc)
    sh.text(PAD + 24, 72, tag.upper(), 26, sh.on(acc), fonts.EXTRABOLD)
    sh.text(W - PAD, 72, "LadsJam", 30, sh.t.ink, fonts.BLACK, align="r")

    size = 96
    while size > 48 and sh.measure(title, size, fonts.BLACK) > W - 2 * PAD:
        size -= 4
    sh.text(PAD, h - 108, title, size, sh.t.ink, fonts.BLACK, max_w=W - 2 * PAD)
    sh.text(PAD, h - 48, subtitle, 34, sh.pal[1], fonts.BOLD, max_w=W - 2 * PAD)
    return h + 36


def _hero_band(sh: Sheet, covers: Sequence[Optional[bytes]], title: str, subtitle: str, tag: str, h: int) -> int:
    """Flat accent block, black slab title, framed cover thumbnails (brutalist)."""
    acc = sh.pal[0]
    ink = sh.t.ink
    sh.rect(0, 0, W, h, acc)
    sh.rect(0, h - 10, W, h, ink)
    tw = sh.measure(tag.upper(), 26, fonts.BLACK)
    sh.chip(PAD, 40, PAD + tw + 48, 94, 0, ink)
    sh.text(PAD + 24, 67, tag.upper(), 26, acc, fonts.BLACK)
    imgs = [i for i in (_open(c) for c in covers) if i][:4]
    tile = min(165, h - 200)
    gap = 14
    tx = W - PAD
    for im in reversed(imgs):
        tx -= tile
        sh.rect(tx - 5 + 8, 40 + 8, tx + tile + 5 + 8, 40 + tile + 5 + 8, ink)
        sh.rect(tx - 5, 35, tx + tile + 5, 45 + tile, ink)
        sh.paste(im, tx, 40, size=tile)
        tx -= gap + 10
    size = 104
    while size > 48 and sh.measure(title, size, fonts.BLACK) > W - 2 * PAD:
        size -= 4
    sh.text(PAD, h - 134, title.upper(), size, ink, fonts.BLACK, max_w=W - 2 * PAD)
    sh.text(PAD, h - 52, subtitle, 34, ink, fonts.BOLD, max_w=W - 2 * PAD)
    return h + 36


def _tilted(im: Image.Image, size: int, angle: float, radius: int, border: int = 6) -> Image.Image:
    """Cover as a white-bordered rounded card rotated by angle (RGBA, pixel units)."""
    full = size + 2 * border
    mask = Image.new("L", (full * 2, full * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, full * 2 - 1, full * 2 - 1], radius=(radius + border) * 2, fill=255)
    card = Image.new("RGBA", (full, full), WHITE + (255,))
    inner = Image.new("L", (size * 2, size * 2), 0)
    ImageDraw.Draw(inner).rounded_rectangle([0, 0, size * 2 - 1, size * 2 - 1], radius=radius * 2, fill=255)
    card.paste(im.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA"), (border, border),
               inner.resize((size, size), Image.Resampling.LANCZOS))
    card.putalpha(mask.resize((full, full), Image.Resampling.LANCZOS))
    return card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)


def _hero_glass(sh: Sheet, covers: Sequence[Optional[bytes]], title: str, subtitle: str, tag: str, h: int) -> int:
    """Blurred cover wall melting into the aurora, frosted tag, three floating glass covers."""
    t = sh.t
    hw, hh = int(W * K), int(h * K)
    wall = _mosaic(sh, covers, hw, hh).filter(ImageFilter.GaussianBlur(int(26 * K)))
    wall = ImageEnhance.Color(wall).enhance(1.3)
    fade, scrim = Image.new("L", (hw, hh)), Image.new("L", (hw, hh))
    fd, sd = ImageDraw.Draw(fade), ImageDraw.Draw(scrim)
    for y in range(hh):
        p = y / hh
        fd.line([(0, y), (hw, y)], fill=int(255 * (1 - p) ** 1.2))  # wall -> backdrop
        sd.line([(0, y), (hw, y)], fill=int(120 * math.sin(math.pi * p) ** 1.2))  # keeps the title legible
    region = Image.composite(wall, sh.img.crop((0, 0, hw, hh)), fade)
    region = Image.composite(Image.new("RGB", (hw, hh), (6, 4, 18)), region, scrim)
    sh.img.paste(region, (0, 0))
    sh.d = ImageDraw.Draw(sh.img)

    tw = sh.measure(tag.upper(), 24, fonts.EXTRABOLD)
    sh.composite(PAD, 44, PAD + tw + 52, 96, 0, lambda d, px: d.rounded_rectangle(
        px(PAD, 44, PAD + tw + 52, 96), radius=int(26 * K), fill=(255, 255, 255, 44), outline=(255, 255, 255, 120),
        width=int(1.6 * K)))
    sh.text(PAD + 26, 70, tag.upper(), 24, t.ink, fonts.EXTRABOLD)

    imgs = [i for i in (_open(c) for c in covers) if i][:3]
    size = 96 if h <= 340 else 150
    gap = 14
    x = W - PAD - size
    for im in imgs:
        sh.soft_shadow(x, 40, x + size, 40 + size, 26, dy=10, alpha=140, blur=10, col=(0, 0, 0))
        sh.paste(im, x, 40, size=size, radius=26)
        sh.rrect(x, 40, x + size, 40 + size, 26, outline=mix(t.bg, WHITE, 0.7), width=2)
        x -= size + gap
    sz = 96
    while sz > 48 and sh.measure(title, sz, fonts.BLACK) > W - 2 * PAD:
        sz -= 4
    sh.text(PAD, h - 108, title, sz, t.ink, fonts.BLACK, max_w=W - 2 * PAD)
    sh.text(PAD, h - 48, subtitle, 34, sh.pal[1], fonts.BOLD, max_w=W - 2 * PAD)
    return h + 36


def _hero_sun(sh: Sheet, title: str, subtitle: str, tag: str, h: int) -> int:
    """Synthwave scene: striped sun on the horizon, neon line, perspective grid, scanlines."""
    t = sh.t
    hw, hh = int(W * K), int(h * K)
    hor = int(hh * 0.64)
    top = mix(t.bg, (0, 0, 0), 0.45)
    glow = mix(t.bg, sh.pal[0], 0.62)
    hero = Image.new("RGB", (hw, hh), t.bg)
    d = ImageDraw.Draw(hero)
    for y in range(hor):
        d.line([(0, y), (hw, y)], fill=mix(top, glow, (y / hor) ** 1.7))

    # sun: vertical gradient disc, cut by stripes that get thicker towards the horizon
    r = int(hh * 0.40)
    cx, cy = int(hw * 0.74), hor - int(r * 0.12)
    sun = Image.new("RGB", (2 * r, 2 * r))
    sd = ImageDraw.Draw(sun)
    for y in range(2 * r):
        p = y / (2 * r)
        sd.line([(0, y), (2 * r, y)], fill=mix((255, 226, 80), (255, 40, 150), p) if p < 0.55 else mix((255, 130, 60), sh.pal[0], (p - 0.55) / 0.45))
    mask = Image.new("L", (2 * r * 2, 2 * r * 2), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, 4 * r - 1, 4 * r - 1], fill=255)
    yy, th = r * 1.5, 3.2 * K * 2  # mask is 2x: the horizon cuts the disc at ~2.24r
    while yy < 4 * r:
        md.rectangle([0, yy, 4 * r, yy + th], fill=0)
        yy += th * 2.1
        th *= 1.3
    hero.paste(sun, (cx - r, cy - r), mask.resize((2 * r, 2 * r), Image.Resampling.LANCZOS))

    # ground + perspective grid
    d = ImageDraw.Draw(hero)
    ground = mix(t.bg, (0, 0, 0), 0.25)
    d.rectangle([0, hor, hw, hh], fill=ground)
    grid = mix(ground, sh.pal[3], 0.55)
    span = hh - hor
    for i in range(1, 7):
        gy = hor + int(span * (i / 6) ** 2)
        d.line([(0, gy), (hw, gy)], fill=grid, width=max(1, int(1.6 * K)))
    for j in range(-14, 15):
        d.line([(hw // 2 + j * 14, hor), (hw // 2 + j * int(hw / 9), hh)], fill=grid, width=max(1, int(1.6 * K)))
    for k, a in enumerate((0.18, 0.4, 1.0)):  # horizon neon line with a soft fall-off above it
        d.rectangle([0, hor - (2 - k) * int(2 * K), hw, hor + int(1.5 * K)], fill=mix(glow, sh.pal[0], a))
    scan = Image.new("RGBA", (hw, hh), (0, 0, 0, 0))
    sc = ImageDraw.Draw(scan)
    for y in range(0, hh, int(4 * K)):
        sc.line([(0, y), (hw, y)], fill=(0, 0, 0, 34))
    sh.img.paste(Image.alpha_composite(hero.convert("RGBA"), scan).convert("RGB"), (0, 0))
    sh.d = ImageDraw.Draw(sh.img)

    acc = sh.pal[0]
    tw = sh.measure(tag.upper(), 26, fonts.EXTRABOLD)
    sh.glow(PAD, 44, PAD + tw + 48, 100, 28, acc, strength=170, spread=10, blur=7)
    sh.rrect(PAD, 44, PAD + tw + 48, 100, 28, fill=acc)
    sh.text(PAD + 24, 72, tag.upper(), 26, sh.on(acc), fonts.EXTRABOLD)
    edge = mix(t.bg, (0, 0, 0), 0.6)
    sh.text(W - PAD, 72, "LadsJam", 30, t.ink, fonts.BLACK, align="r", stroke=(3, edge))
    size = 96
    while size > 48 and sh.measure(title, size, fonts.BLACK) > W - 2 * PAD:
        size -= 4
    sh.text(PAD, h - 108, title, size, t.ink, fonts.BLACK, max_w=W - 2 * PAD, stroke=(5, edge))
    sh.text(PAD, h - 48, subtitle, 34, sh.pal[2], fonts.BOLD, max_w=W - 2 * PAD, stroke=(4, edge))
    return h + 36


def _hero_blob(sh: Sheet, covers: Sequence[Optional[bytes]], title: str, subtitle: str, tag: str, h: int) -> int:
    """Pastel slab with a puffy rounded bottom, floating circles and tilted polaroid covers."""
    t = sh.t
    hw, hh = int(W * K), int(h * K)
    hero = Image.new("RGB", (hw, hh), t.bg)
    d = ImageDraw.Draw(hero)
    d.rounded_rectangle([-int(120 * K), -int(120 * K), hw + int(120 * K), hh - 1], radius=int(88 * K), fill=sh.pal[0])
    for cx, cy, r, ci in ((0.92, 0.12, 120, 2), (0.50, -0.05, 70, 1), (0.04, 0.55, 90, 3), (0.72, 0.9, 54, 1)):
        d.ellipse([int((cx * W - r) * K), int((cy * h - r) * K), int((cx * W + r) * K), int((cy * h + r) * K)],
                  fill=mix(sh.pal[0], sh.pal[ci], 0.8))
    sh.img.paste(hero, (0, 0))
    sh.d = ImageDraw.Draw(sh.img)

    imgs = [i for i in (_open(c) for c in covers) if i][:3]
    size = 150 if h <= 340 else 190
    step = int(size * 0.64)
    left = W - PAD - size - step * (len(imgs) - 1) if imgs else W - PAD
    cy = h * 0.40
    for n, (im, ang) in reversed(list(enumerate(zip(imgs, (6, -5, -9))))):
        card = _tilted(im, int(size * K), ang, int(30 * K), int(7 * K))
        px = int((left + step * n + size / 2) * K - card.width / 2)
        py = int(cy * K - card.height / 2)
        shadow = Image.new("RGBA", card.size, mix(t.line, t.ink, 0.5) + (0,))
        shadow.putalpha(card.getchannel("A").point(lambda v: int(v * 0.3)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(int(10 * K)))
        sh.img.paste(shadow, (px, py + int(12 * K)), shadow)
        sh.img.paste(card, (px, py), card)
    sh.d = ImageDraw.Draw(sh.img)

    tw = sh.measure(tag.upper(), 26, fonts.EXTRABOLD)
    sh.rrect(PAD, 44, PAD + tw + 52, 100, 28, fill=WHITE)
    sh.text(PAD + 26, 72, tag.upper(), 26, t.ink, fonts.EXTRABOLD)
    title_top = h - 108 - 52
    max_w = W - 2 * PAD
    if imgs and cy + size * 0.62 > title_top:
        max_w = int(left - PAD - 24)
    sz = 96
    while sz > 48 and sh.measure(title, sz, fonts.BLACK) > max_w:
        sz -= 4
    sh.text(PAD, h - 108, title, sz, t.ink, fonts.BLACK, max_w=max_w)
    sh.text(PAD, h - 48, subtitle, 34, mix(t.ink, sh.pal[0], 0.15), fonts.BOLD, max_w=max_w)
    return h + 36


def _halftone(gray: Image.Image, cell: int, ink: Tuple[int, int, int]) -> Image.Image:
    """Two-tone dot screen of a grayscale image: white paper, dots in `ink` (RGB), AA via 2x supersampling."""
    w, h = gray.size
    cols, rows = max(1, w // cell), max(1, h // cell)
    small = gray.resize((cols, rows), Image.Resampling.BOX)
    sx = 2
    out = Image.new("RGB", (w * sx, h * sx), WHITE)
    d = ImageDraw.Draw(out)
    for ry in range(rows):
        for cx in range(cols):
            dark = 1 - small.getpixel((cx, ry)) / 255
            if dark < 0.04:
                continue
            r = cell * sx * 0.62 * math.sqrt(dark)
            x = (cx + (0.5 if ry % 2 else 0)) * cell * sx + cell * sx / 2
            y = (ry + 0.5) * cell * sx
            d.ellipse([x - r, y - r, x + r, y + r], fill=ink)
    return out.resize((w, h), Image.Resampling.LANCZOS)


def _hero_halftone(sh: Sheet, covers: Sequence[Optional[bytes]], title: str, subtitle: str, tag: str, h: int) -> int:
    """Riso print: pink + yellow shapes and a blue halftone of the cover wall, overprinted (multiply) on the paper."""
    t = sh.t
    hw = int(W * K)
    bh = h - 190
    bhp = int(bh * K)
    wall = _mosaic(sh, covers, hw, bhp).convert("L")
    wall = ImageEnhance.Contrast(wall).enhance(1.25)
    pink = Image.new("RGB", (hw, bhp), WHITE)
    pd = ImageDraw.Draw(pink)
    pr = int(bhp * 0.78)
    pd.ellipse([int(hw * 0.22) - pr, int(bhp * 0.55) - pr, int(hw * 0.22) + pr, int(bhp * 0.55) + pr], fill=sh.pal[0])
    yel = Image.new("RGB", (hw, bhp), WHITE)
    yr = int(bhp * 0.42)
    ImageDraw.Draw(yel).ellipse([int(hw * 0.74) - yr, int(bhp * 0.34) - yr, int(hw * 0.74) + yr, int(bhp * 0.34) + yr],
                                fill=sh.pal[1])
    blue = _halftone(wall, int(9 * K), t.line)
    region = sh.img.crop((0, 0, hw, bhp))
    for layer in (pink, yel, blue):
        region = ImageChops.multiply(region, layer)
    sh.img.paste(region, (0, 0))
    sh.d = ImageDraw.Draw(sh.img)
    sh.rect(0, bh - 6, W, bh, t.ink)

    tw = sh.measure(tag.upper(), 24, fonts.BLACK)
    sh.chip(PAD, bh + 26, PAD + tw + 44, bh + 72, 0, t.ink)
    sh.text(PAD + 22, bh + 49, tag.upper(), 24, t.bg, fonts.BLACK)
    sh.text(W - PAD, bh + 49, "LadsJam", 26, t.muted, fonts.BOLD, align="r")
    size = 88
    while size > 44 and sh.measure(title, size, fonts.BLACK) > W - 2 * PAD - 8:
        size -= 4
    sh.text(PAD + 5, bh + 127, title, size, sh.pal[0], fonts.BLACK, max_w=W - 2 * PAD - 8)  # misregistered pink plate
    sh.text(PAD, bh + 122, title, size, t.ink, fonts.BLACK, max_w=W - 2 * PAD - 8)
    sh.text(PAD, bh + 170, subtitle, 32, t.line, fonts.BOLD, max_w=W - 2 * PAD)
    return h + 36


def _hero_deco(sh: Sheet, title: str, subtitle: str, tag: str, h: int) -> int:
    """Art deco header: sunburst fan, centred letter-spaced title, gold rule with a diamond."""
    t = sh.t
    gold = sh.pal[0]
    dim = mix(t.bg, gold, 0.2)
    ax, ay = W / 2, h - 30
    for i in range(23):  # rays
        ang = math.radians(200 + i * 140 / 22)
        ln = h * (1.05 if i % 2 == 0 else 0.8)
        sh.d.line([(ax * K, ay * K), ((ax + math.cos(ang) * ln * 1.7) * K, (ay + math.sin(ang) * ln) * K)], fill=dim,
                  width=max(1, int((2.4 if i % 2 == 0 else 1.2) * K)))
    for rr in (70, 130, 190):  # arcs
        sh.d.arc([int((ax - rr * 1.7) * K), int((ay - rr) * K), int((ax + rr * 1.7) * K), int((ay + rr) * K)], 200, 340,
                 fill=mix(t.bg, gold, 0.3), width=max(1, int(1.5 * K)))
    tw = sh.spaced(W / 2, 62, tag.upper(), 22, mix(t.muted, gold, 0.5), fonts.SEMIBOLD, track=6)
    for sx in (W / 2 - tw / 2 - 30, W / 2 + tw / 2 + 30):
        sh.poly([(sx, 55), (sx + 7, 62), (sx, 69), (sx - 7, 62)], fill=gold)
    sh.spaced(W / 2, 160, title.upper(), 76, t.ink, fonts.BLACK, track=5, max_w=W - 2 * PAD - 20)
    sh.spaced(W / 2, 226, subtitle, 30, mix(t.ink, gold, 0.45), fonts.SEMIBOLD, track=2, max_w=W - 2 * PAD - 20)
    ry = h - 40
    sh.rect(PAD + 90, ry, W / 2 - 26, ry + 2, gold)
    sh.rect(W / 2 + 26, ry, W - PAD - 90, ry + 2, gold)
    sh.poly([(W / 2, ry - 12), (W / 2 + 14, ry + 1), (W / 2, ry + 14), (W / 2 - 14, ry + 1)], fill=gold)
    return h + 36


def _hero_plain(sh: Sheet, title: str, subtitle: str, tag: str, h: int) -> int:
    """Text-only header: no imagery, just type and a rule (terminal / minimal)."""
    t = sh.t
    if t.key == "terminal":
        sh.text(PAD, 56, f"$ ladsjam --{tag.replace(' ', '-').lower()}", 28, t.muted, fonts.BOLD)
        sh.text(PAD, 134, title.upper(), 80, t.ink, fonts.BLACK, max_w=W - 2 * PAD)
        sh.text(PAD, 204, "> " + subtitle, 30, sh.pal[1], fonts.BOLD, max_w=W - 2 * PAD)
        sh.rect(PAD, h - 4, W - PAD, h - 2, t.line)
        return h + 36
    sh.label(PAD, 60, tag, t.muted, size=24)
    sh.text(W - PAD, 60, "LadsJam", 24, t.muted, fonts.BOLD, align="r")
    size = 100
    while size > 48 and sh.measure(title, size, fonts.BLACK) > W - 2 * PAD:
        size -= 4
    sh.text(PAD, 138, title, size, t.ink, fonts.BLACK, max_w=W - 2 * PAD)
    sh.text(PAD, 204, subtitle, 32, sh.pal[0], fonts.BOLD, max_w=W - 2 * PAD)
    sh.rect(PAD, h - 4, W - PAD, h - 2, t.ink)
    return h + 36


def _section(sh: Sheet, y: int, num: str, title: str, note: str = "") -> int:
    col = sh.pal[(int(num) - 1) % len(sh.pal)] if num.isdigit() else sh.pal[0]
    if num.isdigit() and sh.t.rank == "roman":
        num = ROMAN[(int(num) - 1) % len(ROMAN)]
    sh.chip(PAD, y, PAD + 72, y + 56, 28, col)
    sh.text(PAD + 36, y + 28, num, 28, sh.on(col), fonts.BLACK, align="m")
    if sh.t.panel == "deco":
        sh.spaced(PAD + 96, y + 28, title.upper(), 34, sh.t.ink, fonts.BLACK, track=3, align="l")
    else:
        sh.text(PAD + 92, y + 28, title.upper(), 38, sh.t.ink, fonts.BLACK)
    if note:
        sh.text(W - PAD, y + 28, note, 26, sh.t.muted, fonts.SEMIBOLD, align="r")
    return y + 88


def _footer(sh: Sheet, y: int, extra: str = "") -> None:
    if sh.t.panel == "deco":
        sh.spaced(W / 2, y + 30, "  ·  ".join(["LADSJAM", sh.t.footer.upper()] + ([extra.upper()] if extra else [])), 22,
                  mix(sh.t.muted, sh.pal[0], 0.4), fonts.SEMIBOLD, track=4, max_w=W - 2 * PAD)
        return
    sh.text(PAD, y + 30, f"LadsJam · {sh.t.footer}", 26, sh.t.muted, fonts.BOLD)
    if extra:
        sh.text(W - PAD, y + 30, extra, 26, sh.t.muted, fonts.BOLD, align="r")


def _kpis(sh: Sheet, y: int, items: Sequence[Tuple[str, str]]) -> int:
    """2x2 grid of big colourful stat cards."""
    gap = 20
    cw = (W - 2 * PAD - gap) // 2
    ch = 190
    for i, (value, label) in enumerate(items):
        r, c = divmod(i, 2)
        x, yy = PAD + c * (cw + gap), y + r * (ch + gap)
        col = sh.pal[i % len(sh.pal)]
        if sh.t.panel in ("fill", "hard", "clay", "riso"):
            sh.chip(x, yy, x + cw, yy + ch, 36, col)
            v_col = l_col = sh.on(col)
        elif sh.t.panel == "outline":
            sh.rrect(x, yy, x + cw, yy + ch, 0, outline=col, width=2)
            v_col, l_col = col, sh.t.muted
        elif sh.t.panel in ("glass", "neon", "deco"):
            sh.panel(x, yy, x + cw, yy + ch, 36, col)
            v_col, l_col = (sh.t.ink if sh.t.panel == "glass" else col), sh.t.muted
            if sh.t.panel == "glass":
                sh.rrect(x + 28, yy + 166, x + 92, yy + 171, 3, fill=col)
        else:
            sh.rect(x, yy, x + cw, yy + 4, sh.t.ink)
            v_col, l_col = sh.t.ink, sh.t.muted
        size = 84
        while size > 36 and sh.measure(value, size, fonts.BLACK) > cw - 56:
            size -= 4
        sh.text(x + 28, yy + 84, value, size, v_col, fonts.BLACK)
        label_size = 26
        while label_size > 16 and sh.measure(label.upper(), label_size, fonts.EXTRABOLD) > cw - 56:
            label_size -= 1
        sh.text(x + 28, yy + 148, label.upper(), label_size, l_col, fonts.EXTRABOLD)
    rows = math.ceil(len(items) / 2)
    return y + rows * (ch + gap)


def _bars(sh: Sheet, y: int, h: int, values: Sequence[int], labels: Sequence[str],
          show_values: bool, label_every: int = 1, *, x0: float = PAD,
          x1: float = W - PAD, label_size: int = 24) -> int:
    sh.panel(x0 - 12, y, x1 + 12, y + h, 36)
    top, bottom = y + 60, y + h - 56
    vmax = max(max(values, default=0), 1)
    n = max(1, len(values))
    slot = (x1 - x0 - 24) / n
    bw = max(8, slot * (0.62 if n <= 14 else 0.72))
    imax = values.index(max(values)) if any(values) else -1
    for i, v in enumerate(values):
        cx = x0 + 12 + slot * i + slot / 2
        if v > 0:
            bh = max(10, (bottom - top) * v / vmax)
            col = sh.pal[1] if i == imax else sh.pal[0]
            sh.bar(cx - bw / 2, bottom - bh, cx + bw / 2, bottom, min(10, bw / 2), col)
            if show_values:
                sh.text(cx, bottom - bh - 20, v, 24, sh.t.ink, fonts.BOLD, align="m")
        else:
            sh.rrect(cx - bw / 2, bottom - 6, cx + bw / 2, bottom, 3, fill=sh.t.line)
        if i % label_every == 0:
            sh.text(cx, bottom + 30, labels[i], label_size, sh.t.muted, fonts.SEMIBOLD, align="m")
    return y + h


def _rank_list(sh: Sheet, y: int, rows: Sequence[Row], unit: str = "") -> int:
    vmax = max([r[2] for r in rows], default=1) or 1
    for i, (label, sub, val) in enumerate(rows):
        row_h = 128 if sub else 108
        col = sh.pal[i % len(sh.pal)]
        sh.panel(PAD - 12, y, W - PAD + 12, y + row_h - 14, 30, col)
        # proportional fill strip along the bottom
        bw = int((W - 2 * PAD - 24) * val / vmax)
        sh.bar(PAD, y + row_h - 26, PAD + max(bw, 12), y + row_h - 20, 3, col)
        cy = y + (row_h - 26) / 2
        if sh.t.rank == "pill":
            sh.chip(PAD, cy - 30, PAD + 60, cy + 30, 30, col)
            sh.text(PAD + 30, cy, f"{i + 1}", 30, sh.on(col), fonts.BLACK, align="m")
        elif sh.t.rank == "roman":
            sh.text(PAD + 8, cy, ROMAN[i % len(ROMAN)], 30, sh.fg(col), fonts.BLACK)
        else:
            num = f"{i + 1:02d}" if sh.t.rank == "mono" else str(i + 1)
            sh.text(PAD + 30, cy, num, 36, sh.fg(col), fonts.BLACK, align="m")
        tx = PAD + (92 if sh.t.rank == "roman" else 84)
        vtxt = f"{val:,}".replace(",", " ")
        vw = sh.measure(vtxt, 36, fonts.BLACK)
        maxw = W - PAD - tx - vw - 28
        if sub:
            sh.text(tx, cy - 20, label, 36, sh.t.ink, fonts.EXTRABOLD, max_w=maxw)
            sh.text(tx, cy + 22, sub, 28, sh.t.muted, fonts.SEMIBOLD, max_w=maxw)
        else:
            sh.text(tx, cy, label, 36, sh.t.ink, fonts.EXTRABOLD, max_w=maxw)
        sh.text(W - PAD - 12, cy, vtxt, 36, sh.fg(col), fonts.BLACK, align="r")
        y += row_h
    return y


def _fmt_time(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}ч {m:02d}м" if h else f"{m}м"


def _rows_h(n: int, sub: bool) -> int:
    return n * (128 if sub else 108)


# ---- public renderers --------------------------------------------------------
def _stats_ranking(sh: Sheet, x: int, y: int, width: int, title: str, rows: Sequence[Row]) -> int:
    """Half-width ranking panel for the compact listening report."""
    height = 80 + max(len(rows), 1) * 92 + 16
    sh.panel(x, y, x + width, y + height, 28)
    sh.text(x + 24, y + 38, title, 28, sh.t.ink, fonts.BLACK, max_w=width - 48)
    vmax = max((row[2] for row in rows), default=1) or 1
    if not rows:
        sh.text(x + 24, y + 112, "Пока нет данных", 26, sh.t.muted)
    for i, (label, sub, val) in enumerate(rows):
        ry = y + 80 + i * 92
        col = sh.pal[i % len(sh.pal)]
        sh.text(x + 24, ry + 25, str(i + 1), 26, sh.fg(col), fonts.BLACK)
        value = f"{val:,}".replace(",", " ")
        vw = sh.measure(value, 28, fonts.BLACK)
        sh.text(x + width - 24, ry + 25, value, 28, sh.fg(col), fonts.BLACK, align="r")
        sh.text(x + 58, ry + 25, label, 28, sh.t.ink, fonts.EXTRABOLD, max_w=width - 106 - vw)
        if sub:
            sh.text(x + 58, ry + 55, sub, 23, sh.t.muted, fonts.SEMIBOLD, max_w=width - 82)
        bw = max(6, (width - 82) * val / vmax)
        sh.bar(x + 58, ry + 74, x + 58 + bw, ry + 79, 2, col)
    return y + height


def render_stats(st: ListeningStats, covers: Sequence[Optional[bytes]] = (), theme: Theme = DEFAULT) -> io.BytesIO:
    hero_h = _hero_h(theme, 280)
    charts_y = hero_h + 36 + 20 + 2 * 210 + 24
    ranks_y = charts_y + 390
    rank_h = 80 + max(len(st.top_artists), len(st.top_tracks), 1) * 92 + 16
    height = ranks_y + rank_h + 100
    sh = Sheet(height, _palette(covers, theme), theme)
    y = _hero(sh, covers, st.name.upper(), f"последние {st.days} дн.", "listening report", hero_h)
    _kpis(
        sh, y + 20,
        [
            (f"{st.total:,}".replace(",", " "), "количество прослушиваний"),
            (_fmt_time(st.minutes), "время ≈"),
            (str(st.unique_artists), "артистов"),
            (f"{st.streak} дн.", "серия"),
        ],
    )

    gap = 32
    panel_w = (W - 2 * PAD - gap) // 2
    right_x = PAD + panel_w + gap
    sh.text(PAD, charts_y + 20, "ПО ДНЯМ", 30, sh.t.ink, fonts.BLACK)
    sh.text(right_x, charts_y + 20, "ПО ЧАСАМ", 30, sh.t.ink, fonts.BLACK)
    n = len(st.per_day)
    _bars(sh, charts_y + 60, 270, [v for _, v in st.per_day], [l for l, _ in st.per_day],
          show_values=n <= 7, label_every=max(1, math.ceil(n / 5)),
          x0=PAD, x1=PAD + panel_w, label_size=20)
    _bars(sh, charts_y + 60, 270, st.per_hour, [f"{h:02d}" for h in range(24)], False, 4,
          x0=right_x, x1=W - PAD, label_size=20)
    sh.text(PAD, charts_y + 354, f"Рекорд: {st.best_day[1]} · {st.best_day[0]}", 23, sh.t.muted,
            max_w=panel_w)
    peak = max(range(24), key=lambda h: st.per_hour[h]) if st.total else 0
    sh.text(right_x, charts_y + 354, f"Пик активности: {peak:02d}:00", 23, sh.t.muted)
    _stats_ranking(sh, PAD, ranks_y, panel_w, "ТОП АРТИСТОВ", st.top_artists)
    _stats_ranking(sh, right_x, ranks_y, panel_w, "ТОП ТРЕКОВ", st.top_tracks)
    _footer(sh, ranks_y + rank_h + 24, "выборка ограничена" if st.truncated else "")
    return sh.export()


def render_rows(title: str, subtitle: str, rows: Sequence[Row], unit_note: str = "", tag: str = "chart",
                covers: Sequence[Optional[bytes]] = (), theme: Theme = DEFAULT) -> io.BytesIO:
    rows = list(rows)[:15]
    has_sub = any(r[1] for r in rows)
    hero_h = _hero_h(theme, 460)
    height = hero_h + 36 + 20 + 88 + _rows_h(len(rows), has_sub) + 100
    sh = Sheet(height, _palette(covers, theme), theme)
    y = _hero(sh, covers, title, subtitle, tag, hero_h)
    y = _section(sh, y + 20, "1", unit_note or "рейтинг")
    y = _rank_list(sh, y, rows)
    _footer(sh, y + 24)
    return sh.export()


def render_album_grid(
    title: str, subtitle: str, items: Sequence[dict], covers: Sequence[Optional[bytes]], theme: Theme = DEFAULT
) -> io.BytesIO:
    items = list(items)[:9]
    covers = list(covers)
    n = len(items)
    cols = 3 if n >= 5 else 2 if n > 1 else 1
    rows = math.ceil(n / cols)
    gap = 24
    size = min(600, (W - 2 * PAD - gap * (cols - 1)) // cols)
    grid_x = (W - (cols * size + (cols - 1) * gap)) // 2
    cap_h = 104
    cell_h = size + cap_h
    hero_h = _hero_h(theme, 280)
    height = hero_h + 36 + 20 + rows * cell_h + 100
    sh = Sheet(height, _palette(covers, theme), theme)
    y0 = _hero(sh, covers, title, subtitle, "top albums", hero_h) + 20
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x = grid_x + c * (size + gap)
        y = y0 + r * cell_h
        col = sh.pal[i % len(sh.pal)]
        im = _open(covers[i] if i < len(covers) else None) or Image.new("RGB", (size, size), sh.t.card)
        sh.edge_under(x, y, size, col)
        sh.paste(im, x, y, size=size, radius=32)
        sh.edge_over(x, y, size, col)
        sh.chip(x + 16, y + 16, x + 16 + 76, y + 16 + 76, 38, col)
        sh.text(x + 54, y + 54, f"{i + 1}", 36, sh.on(col), fonts.BLACK, align="m")
        pl = f"{it['plays']}"
        pw = sh.measure(pl, 30, fonts.BLACK) + 40
        sh.rrect(x + size - 16 - pw, y + size - 76, x + size - 16, y + size - 16, 30, fill=(12, 12, 16))
        sh.text(x + size - 16 - pw / 2, y + size - 46, pl, 30, col if sh.t.key != "minimal" else (250, 250, 250),
                fonts.BLACK, align="m")
        sh.text(x + 4, y + size + 30, it["name"], 28, sh.t.ink, fonts.EXTRABOLD, max_w=size - 8)
        sh.text(x + 4, y + size + 66, it["artist"], 24, sh.t.muted, fonts.SEMIBOLD, max_w=size - 8)
    _footer(sh, y0 + rows * cell_h + 10)
    return sh.export()


def render_versus(
    name_a: str, name_b: str, subtitle: str, metrics: Sequence[Tuple[str, int, int]],
    covers: Sequence[Optional[bytes]] = (), theme: Theme = DEFAULT,
) -> io.BytesIO:
    hero_h = _hero_h(theme, 460)
    height = hero_h + 36 + 20 + 150 * len(metrics) + 110
    sh = Sheet(height, _palette(covers, theme), theme)
    y = _hero(sh, covers, f"{name_a} vs {name_b}", subtitle, "versus", hero_h) + 20
    wins_a = sum(1 for _, a, b in metrics if a > b)
    wins_b = sum(1 for _, a, b in metrics if b > a)
    cx = W / 2
    half = cx - PAD
    ca, cb = sh.pal[0], sh.pal[2]
    loser = tuple(int(l * 0.25 + b * 0.75) for l, b in zip(sh.t.line, sh.t.bg))
    for label, a, b in metrics:
        sh.panel(PAD - 12, y, W - PAD + 12, y + 132, 34)
        sh.label(cx, y + 30, label, sh.t.muted, align="m", size=24)
        m = max(a, b, 1)
        by = y + 92
        wa, wb = int((half - 190) * a / m), int((half - 190) * b / m)
        sh.bar(cx - 12 - max(wa, 10), by - 18, cx - 12, by + 18, 14, ca if a >= b else loser)
        sh.bar(cx + 12, by - 18, cx + 12 + max(wb, 10), by + 18, 14, cb if b >= a else loser)
        sh.text(PAD + 8, by, f"{a:,}".replace(",", " "), 44, sh.fg(ca), fonts.BLACK)
        sh.text(W - PAD - 8, by, f"{b:,}".replace(",", " "), 44, sh.fg(cb), fonts.BLACK, align="r")
        y += 150
    _footer(sh, y + 10, f"{wins_a} : {wins_b}")
    return sh.export()
