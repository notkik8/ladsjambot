"""Formatting for displayed Telegram names; stored names keep their @ for lookups."""
import html
from urllib.parse import quote

from aiogram.utils.formatting import CustomEmoji, Text, TextLink


def user_name(name: str) -> str:
    """Keep names readable without producing Telegram @mentions."""
    return name.replace("@", "")


def user_name_html(name: str) -> str:
    """Show a name as HTML text without creating @mentions, including in full names."""
    return html.escape(user_name(name))


def spotify_search_url(artist: str, track: str) -> str:
    """Open Spotify search without requiring API credentials."""
    return "https://open.spotify.com/search/" + quote(f"{artist} {track}", safe="")


# (fallback emoji, name, search URL prefix, premium custom-emoji id from t.me/addemoji/ApplicationEmoji)
SERVICES = (
    ("🟢", "Spotify", "https://open.spotify.com/search/", "5346074681004801565"),
    ("🍎", "Apple Music", "https://music.apple.com/search?term=", "5346251367369425932"),
    ("▶️", "YouTube", "https://www.youtube.com/results?search_query=", "5334681713316479679"),
    ("🔴", "YT Music", "https://music.youtube.com/search?q=", ""),
    ("🟡", "Яндекс Музыка", "https://music.yandex.ru/search?text=", ""),
    ("🔵", "VK Музыка", "https://vk.com/audio?q=", "5334853932915114338"),
    ("☁️", "SoundCloud", "https://soundcloud.com/search?q=", "5345844509412444249"),
    ("🟣", "Deezer", "https://www.deezer.com/search/", "5345845252441784353"),
)


def listen_links(artist: str, track: str) -> list[tuple[str, str, str]]:
    """Search links for the track on every supported service: (emoji, name, url)."""
    q = quote(f"{artist} {track}", safe="")
    return [(emoji, name, prefix + q) for emoji, name, prefix, _ in SERVICES]


def services_legend() -> str:
    return " · ".join(f"{emoji} {name}" for emoji, name, _, _ in SERVICES)


def listen_link_nodes(artist: str, track: str, premium: bool = True) -> list:
    """Clickable emoji row; services in the premium pack get an animated custom emoji.

    Telegram shows the fallback emoji to everyone who can't see custom emoji
    (no Premium, or a bot that isn't allowed to send them), so nothing breaks.
    """
    nodes: list = []
    for (emoji, _name, _prefix, emoji_id), (_, _, url) in zip(SERVICES, listen_links(artist, track)):
        label = CustomEmoji(emoji, custom_emoji_id=emoji_id) if premium and emoji_id else emoji
        nodes.extend([TextLink(label, url=url), " "])
    return nodes[:-1]


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
