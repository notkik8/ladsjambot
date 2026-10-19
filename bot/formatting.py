"""Formatting for displayed Telegram names; stored names keep their @ for lookups."""
import html
from urllib.parse import quote

from aiogram.utils.formatting import Text


def user_name(name: str) -> str:
    """Keep names readable without producing Telegram @mentions."""
    return name.replace("@", "")


def user_name_html(name: str) -> str:
    """Show a name as HTML text without creating @mentions, including in full names."""
    return html.escape(user_name(name))


def spotify_search_url(artist: str, track: str) -> str:
    """Open Spotify search without requiring API credentials."""
    return "https://open.spotify.com/search/" + quote(f"{artist} {track}", safe="")


# (emoji, name, search URL prefix, how the query is appended)
SERVICES = (
    ("🟢", "Spotify", "https://open.spotify.com/search/", ""),
    ("🍎", "Apple Music", "https://music.apple.com/search?term=", ""),
    ("▶️", "YouTube", "https://www.youtube.com/results?search_query=", ""),
    ("🔴", "YT Music", "https://music.youtube.com/search?q=", ""),
    ("🟡", "Яндекс Музыка", "https://music.yandex.ru/search?text=", ""),
    ("☁️", "SoundCloud", "https://soundcloud.com/search?q=", ""),
    ("🟣", "Deezer", "https://www.deezer.com/search/", ""),
)


def listen_links(artist: str, track: str) -> list[tuple[str, str, str]]:
    """Search links for the track on every supported service: (emoji, name, url)."""
    q = quote(f"{artist} {track}", safe="")
    return [(emoji, name, prefix + q) for emoji, name, prefix, _ in SERVICES]


def services_legend() -> str:
    return " · ".join(f"{emoji} {name}" for emoji, name, _, _ in SERVICES)


def now_playing_html_chunks(content: Text) -> list[str]:
    """Split a caption and follow-up messages without breaking links or Unicode.

    Telegram limits apply to rendered text, not the HTML markup or link URLs.
    Entity offsets use UTF-16 units, so an emoji can take two units.
    """
    text, entities = content.render()
    chunks = []
    start = offset = 0
    limit = 1024
    while start < len(text):
        end = start
        units = 0
        while end < len(text):
            char_units = 2 if ord(text[end]) > 0xFFFF else 1
            if units + char_units > limit:
                break
            units += char_units
            end += 1
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline + 1
        piece = text[start:end]
        size = len(piece.encode("utf-16-le")) // 2
        piece_entities = []
        for entity in entities:
            left = max(entity.offset, offset)
            right = min(entity.offset + entity.length, offset + size)
            if left < right:
                piece_entities.append(entity.model_copy(update={"offset": left - offset, "length": right - left}))
        chunks.append(Text.from_entities(piece, piece_entities).as_html())
        start = end
        offset += size
        limit = 4096
    return chunks
