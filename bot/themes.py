"""Event themes for rendered images: palettes, greetings and which stickers to scatter."""
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple

RGB = Tuple[int, int, int]

AUTO = "auto"


@dataclass(frozen=True)
class Theme:
    key: str
    title: str
    emoji: str
    footer: str  # shown in the image footer next to the brand
    bg: RGB
    card: RGB
    line: RGB
    muted: RGB
    palette: Tuple[RGB, ...]  # 4 accent colours; empty -> derived from cover art
    stickers: Tuple[str, ...] = ()
    ink: RGB = (255, 255, 255)

    @property
    def themed(self) -> bool:
        return bool(self.stickers)


THEMES = {
    t.key: t
    for t in (
        Theme(
            "default", "Стандартная", "🎵", "Last.fm",
            bg=(11, 9, 20), card=(27, 23, 46), line=(52, 46, 80), muted=(178, 174, 200),
            palette=(),
        ),
        Theme(
            "halloween", "Хэллоуин", "🎃", "Счастливого Хэллоуина",
            bg=(17, 8, 23), card=(36, 19, 46), line=(78, 44, 92), muted=(206, 176, 220),
            palette=((255, 122, 0), (170, 100, 255), (150, 230, 40), (255, 80, 110)),
            stickers=("pumpkin", "bat", "ghost"),
        ),
        Theme(
            "newyear", "Новый год", "🎄", "С Новым годом!",
            bg=(6, 14, 32), card=(14, 31, 60), line=(42, 72, 112), muted=(170, 196, 226),
            palette=((255, 72, 84), (255, 214, 90), (80, 200, 255), (110, 232, 150)),
            stickers=("snowflake", "ornament", "tree", "snowflake"),
        ),
        Theme(
            "maslenitsa", "Масленица", "🥞", "Широкой Масленицы!",
            bg=(30, 16, 6), card=(58, 33, 12), line=(112, 72, 30), muted=(228, 202, 160),
            palette=((255, 184, 28), (255, 112, 40), (255, 228, 120), (236, 72, 60)),
            stickers=("pancake", "sun", "pancake"),
        ),
        Theme(
            "easter", "Пасха", "🥚", "Светлой Пасхи!",
            bg=(24, 22, 46), card=(42, 38, 74), line=(84, 78, 128), muted=(206, 202, 232),
            palette=((255, 182, 213), (190, 240, 150), (255, 238, 140), (160, 210, 255)),
            stickers=("egg", "egg", "sun"),
        ),
        Theme(
            "valentine", "14 февраля", "💘", "С Днём всех влюблённых",
            bg=(30, 8, 23), card=(56, 17, 42), line=(110, 40, 80), muted=(236, 186, 212),
            palette=((255, 70, 120), (255, 150, 190), (255, 130, 90), (205, 110, 255)),
            stickers=("heart",),
        ),
    )
}

ORDER = ["default", "halloween", "newyear", "maslenitsa", "easter", "valentine"]


def _orthodox_easter(year: int) -> dt.date:
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month, day = divmod(d + e + 114, 31)
    return dt.date(year, month, day + 1) + dt.timedelta(days=13)  # Julian -> Gregorian (1900-2099)


def seasonal_key(today: Optional[dt.date] = None) -> str:
    """Theme key that fits the date (used when a chat picked "auto")."""
    d = today or dt.date.today()
    md = (d.month, d.day)
    if md >= (12, 15) or md <= (1, 14):
        return "newyear"
    if (10, 20) <= md <= (11, 2):
        return "halloween"
    if (2, 10) <= md <= (2, 14):
        return "valentine"
    easter = _orthodox_easter(d.year)
    if easter - dt.timedelta(days=56) <= d <= easter - dt.timedelta(days=49):
        return "maslenitsa"
    if easter - dt.timedelta(days=7) <= d <= easter + dt.timedelta(days=7):
        return "easter"
    return "default"


def resolve(key: Optional[str], today: Optional[dt.date] = None) -> Theme:
    if key == AUTO:
        key = seasonal_key(today)
    return THEMES.get(key or "default", THEMES["default"])


DEFAULT = THEMES["default"]


async def for_chat(db, chat_id: int) -> Theme:
    """Theme chosen for a chat (falls back to default if the lookup fails)."""
    try:
        return resolve(await db.get_chat_theme(chat_id))
    except Exception:
        return DEFAULT
