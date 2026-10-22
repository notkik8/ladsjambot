"""
Pillow renderers for stats images - phone-first.

Design: loud, colourful "poster" look. Full-bleed cover mosaic hero, heavy Montserrat type,
big numbers, per-image palette taken from the covers, glow blobs behind everything.
Logical width is 1080 (text sizes are chosen so it stays readable at ~390pt phone width).
"""
import io
import math
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from bot import fonts
from bot.collage import _dominant
from bot.stats import ListeningStats
from bot.themes import DEFAULT, Theme

K = 1.5  # render scale (keeps width+height under Telegram's 10000px photo limit)
W = 1080
PAD = 48

DEFAULT_PALETTE = [(255, 61, 129), (255, 214, 10), (0, 229, 255), (150, 100, 255)]

Row = Tuple[str, str, int]  # label, sublabel, value


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
        lum = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
        return (12, 12, 16) if lum > 140 else (250, 250, 250)

    def fg(self, col) -> Tuple[int, int, int]:
        """Accent colour for text; on light themes bright accents (yellow) fall back to ink for contrast."""
        lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
        return self.t.ink if lum(self.t.bg) > 140 and lum(col) > 120 else col

    def chip(self, x0, y0, x1, y1, r, col):
        """Solid accent block (badge / KPI); hard style gets a thick outline + offset shadow."""
        if self.t.panel == "hard":
            self.rect(x0 + 7, y0 + 7, x1 + 7, y1 + 7, self.t.line)
            self.rrect(x0, y0, x1, y1, r, fill=col, outline=self.t.line, width=4)
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

    # text -----------------------------------------------------------------
    def measure(self, s: str, size: float, weight=fonts.BOLD) -> float:
        return fonts.font(max(8, int(size * K)), weight).getlength(s) / K

    def text(self, x, y, s, size, fill=None, weight=fonts.BOLD, align="l", max_w=None) -> float:
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
        self.d.text((x * K, y * K), s, font=fonts.font(max(8, int(size * K)), weight), fill=fill, anchor="lm")
        return w

    def label(self, x, y, s, fill=None, align="l", size=24):
        return self.text(x, y, s.upper(), size, fill or self.t.muted, fonts.SEMIBOLD, align)

    def bar(self, x0, y0, x1, y1, r, col):
        """Horizontal or vertical bar; terminal-style themes cut it into blocks."""
        if not self.t.bar_blocks:
            if self.t.panel == "hard":
                self.rrect(x0, y0, x1, y1, r, fill=col, outline=self.t.line, width=3)
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
    """Plain (text-only) heroes are compact."""
    if theme.hero == "band":
        return max(h, 400)
    return 250 if theme.hero == "plain" else h


def _hero(sh: Sheet, covers: Sequence[Optional[bytes]], title: str, subtitle: str, tag: str, h: int = 520) -> int:
    """Top block: cover-mosaic wall, flat colour band or plain text, depending on the theme."""
    h = _hero_h(sh.t, h)
    if sh.t.hero == "plain":
        return _hero_plain(sh, title, subtitle, tag, h)
    if sh.t.hero == "band":
        return _hero_band(sh, covers, title, subtitle, tag, h)
    imgs = [i for i in (_open(c) for c in covers) if i]
    hw, hh = int(W * K), int(h * K)
    hero = Image.new("RGB", (hw, hh), sh.t.card)
    if imgs:
        cols = 4 if len(imgs) >= 8 else 3 if len(imgs) >= 4 else 2
        tile = math.ceil(hw / cols)
        rows = math.ceil(hh / tile) + 1
        for i in range(cols * rows):
            t = imgs[i % len(imgs)].resize((tile, tile), Image.Resampling.LANCZOS)
            hero.paste(t, ((i % cols) * tile, (i // cols) * tile))
        hero = ImageEnhance.Color(hero).enhance(1.25)
    else:
        d = ImageDraw.Draw(hero)
        for i, col in enumerate(sh.pal):
            cx, cy, r = int(hw * (0.15 + 0.25 * i)), int(hh * (0.3 + 0.35 * (i % 2))), int(hh * 0.55)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        hero = hero.filter(ImageFilter.GaussianBlur(int(60 * K)))
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
    sh.chip(PAD, y, PAD + 72, y + 56, 28, col)
    sh.text(PAD + 36, y + 28, num, 28, sh.on(col), fonts.BLACK, align="m")
    sh.text(PAD + 92, y + 28, title.upper(), 38, sh.t.ink, fonts.BLACK)
    if note:
        sh.text(W - PAD, y + 28, note, 26, sh.t.muted, fonts.SEMIBOLD, align="r")
    return y + 88


def _footer(sh: Sheet, y: int, extra: str = "") -> None:
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
        if sh.t.panel in ("fill", "hard"):
            sh.chip(x, yy, x + cw, yy + ch, 36, col)
            v_col = l_col = sh.on(col)
        elif sh.t.panel == "outline":
            sh.rrect(x, yy, x + cw, yy + ch, 0, outline=col, width=2)
            v_col, l_col = col, sh.t.muted
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
        else:
            num = f"{i + 1:02d}" if sh.t.rank == "mono" else str(i + 1)
            sh.text(PAD + 30, cy, num, 36, sh.fg(col), fonts.BLACK, align="m")
        tx = PAD + 84
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
        sh.paste(im, x, y, size=size, radius=32)
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
