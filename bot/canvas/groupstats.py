"""One listener's animated ten-second group statistics scene."""
import colorsys
import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from bot.fonts import font, symbol_font, BOLD, EXTRABOLD, SEMIBOLD


class GroupStatsFrames:
    def __init__(self, username: str, artist: str, title: str, plays: int,
                 avatar_bytes: bytes | None, cover_bytes: bytes | None, theme, size=720):
        self.width = self.height = size
        self.scale = size / 720
        self.theme = theme
        self.side = self._s(340)
        self.top = self._s(60)
        avatar = self._image(avatar_bytes)
        self.accent = self._accent(avatar, theme)
        if avatar is None:
            avatar = Image.new('RGB', (self.side, self.side), theme.card)
            draw = ImageDraw.Draw(avatar)
            initials = ''.join(part[0] for part in username.strip().lstrip('@').split()[:2]).upper() or '?'
            text, face = self._fit(initials, self._s(112), EXTRABOLD, self.side * .8)
            draw.text((self.side / 2, self.side / 2), text, font=face, fill=theme.ink, anchor='mm')
        cover = self._image(cover_bytes)
        if cover is None:
            cover = Image.new('RGB', (self.side, self.side), theme.card)
            ImageDraw.Draw(cover).text((self.side / 2, self.side / 2), '♪',
                                       font=symbol_font(self._s(120)), fill=theme.muted, anchor='mm')
        self.avatar = self._rounded(avatar)
        self.cover = self._rounded(cover)
        self.background = Image.new('RGB', (size, size), theme.bg)
        glow = Image.new('RGBA', (size, size))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((self._s(130), self._s(20), self._s(590), self._s(480)), fill=(*self.accent, 35))
        glow = glow.filter(ImageFilter.GaussianBlur(self._s(90)))
        self.background = Image.alpha_composite(self.background.convert('RGBA'), glow).convert('RGB')
        self.name = self._text_layer([(username or '?', 38, EXTRABOLD, theme.ink)])
        self.track = self._text_layer([(f'{artist} — {title}', 32, EXTRABOLD, theme.ink),
                                      (self._plays(plays), 22, SEMIBOLD, theme.muted)])
        # Blur once, not for each frame; blend these layers during the text change.
        self.name_blur = self.name.filter(ImageFilter.GaussianBlur(self._s(8)))
        self.track_blur = self.track.filter(ImageFilter.GaussianBlur(self._s(8)))

    def _s(self, value):
        return max(1, round(value * self.scale))

    def _image(self, raw):
        if not raw:
            return None
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.width * image.height > 16_000_000:
                    return None
                image.thumbnail((self.side * 2, self.side * 2))
                image = ImageOps.exif_transpose(image).convert('RGB')
                return ImageOps.fit(image, (self.side, self.side), method=Image.Resampling.LANCZOS)
        except (OSError, ValueError, Image.DecompressionBombError):
            return None

    @staticmethod
    def _accent(image, theme):
        if image is None:
            return theme.palette[0] if theme.palette else theme.muted
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in image.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))))
        return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, max(.4, s), max(.7, v)))

    def _rounded(self, image):
        mask = Image.new('L', image.size)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1),
                                               radius=self._s(24), fill=255)
        result = image.convert('RGBA')
        result.putalpha(mask)
        return result

    @staticmethod
    def _fit(text, size, weight, width):
        text = str(text or '?').replace('\n', ' ')
        for step in range(7):
            face = font(max(8, round(size * (1 - .06 * step))), weight)
            if face.getlength(text) <= width:
                return text, face
        while len(text) > 1 and face.getlength(text + '…') > width:
            text = text[:-1]
        return text.rstrip() + '…', face

    @staticmethod
    def _plays(value):
        n = max(0, int(value))
        ending = 'прослушивание' if n % 10 == 1 and n % 100 != 11 else (
            'прослушивания' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'прослушиваний')
        return f'{n} {ending}'

    def _text_layer(self, lines):
        layer = Image.new('RGBA', (self.width, self._s(110)))
        draw = ImageDraw.Draw(layer)
        y = self._s(7)
        for text, size, weight, colour in lines:
            text, face = self._fit(text, self._s(size), weight, self.width - self._s(72))
            draw.text((self.width / 2, y), text, font=face, fill=colour, anchor='mt')
            y += face.size + self._s(12)
        return layer

    @staticmethod
    def _ease(value):
        p = min(1., max(0., value))
        return p * p * (3 - 2 * p)

    @staticmethod
    def _paste(canvas, image, position, alpha=1.):
        if alpha <= 0:
            return
        if alpha < 1:
            image = image.copy()
            image.putalpha(image.getchannel('A').point(lambda value: round(value * alpha)))
        canvas.paste(image, position, image)

    def motion(self, index, t, seconds, previous, bars, fps, samples=4, came_from=None):
        # Scene contents travel together; the background remains stable between scenes.
        entry = self._ease(t / .8)
        exit_progress = self._ease((t - 9.2) / .8)
        dx = round(-self.width * (1 - entry) + self.width * exit_progress)
        layer = Image.new('RGBA', (self.width, self.height))
        flip = self._ease((t - 1.3) / 1.)
        face = self.avatar if flip < .5 else self.cover
        width = max(1, round(self.side * abs(math.cos(math.pi * flip))))
        card = face.resize((width, self.side), Image.Resampling.BILINEAR)
        self._paste(layer, card, ((self.width - width) // 2, self.top))
        text_y = self._s(430)
        # Text dissolves through blurred forms while moving vertically.
        self._paste(layer, self.name, (0, text_y - round(self._s(12) * flip)), 1 - flip)
        self._paste(layer, self.name_blur, (0, text_y - round(self._s(12) * flip)), 4 * flip * (1 - flip) * .35)
        self._paste(layer, self.track_blur, (0, text_y + round(self._s(12) * (1 - flip))), 4 * flip * (1 - flip) * .35)
        self._paste(layer, self.track, (0, text_y + round(self._s(12) * (1 - flip))), flip)
        draw = ImageDraw.Draw(layer)
        values = np.asarray(bars, dtype=float).flatten()
        count = min(16, len(values))
        bw = self._s(10); gap = self._s(8)
        left = (self.width - (count * bw + max(0, count - 1) * gap)) // 2
        centre = self._s(593)
        for i in range(count):
            value = float(np.clip(values[i], 0, 1))
            height = self._s(5) + round(value * self._s(48))
            x = left + i * (bw + gap)
            draw.rounded_rectangle((x, centre - height // 2, x + bw, centre + height // 2),
                                   radius=bw // 2, fill=(*self.accent, round(255 * flip)))
        result = self.background.copy()
        self._paste(result, layer, (dx, 0))
        return result
