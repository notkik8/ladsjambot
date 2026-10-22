import unittest

from PIL import Image

from bot import themes
from bot.collage import build_collage
from bot.infographic import render_album_grid, render_rows, render_stats, render_versus
from bot.lastfm import TrackInfo
from bot.stats import ListeningStats


def _stats() -> ListeningStats:
    return ListeningStats(
        name="listener", days=7, total=42, unique_artists=5, unique_tracks=20, active_days=5, minutes=150, streak=3,
        per_day=[(f"{d:02d}.10", d % 5) for d in range(1, 8)], per_hour=[i % 4 for i in range(24)],
        top_artists=[(f"Artist {i}", "", 9 - i) for i in range(5)],
        top_tracks=[(f"Track {i}", f"Artist {i}", 9 - i) for i in range(5)],
        best_day=("03.10", 4),
    )


class ThemeRenderTests(unittest.TestCase):
    def test_order_lists_every_theme_once(self):
        self.assertEqual(sorted(themes.ORDER), sorted(themes.THEMES))
        self.assertEqual(len(set(themes.ORDER)), len(themes.ORDER))

    def test_every_theme_renders_every_image_without_artwork(self):
        rows = [(f"Очень длинное название исполнителя номер {i}", "Артист", 100 - i) for i in range(15)]
        albums = [{"name": f"Album {i}", "artist": "Artist", "plays": 50 - i} for i in range(9)]
        metrics = [("Артисты", 10, 4), ("Треки", 3, 3)]
        infos = [TrackInfo(i, f"Listener {i}", "u", "Artist", "Track " * 6) for i in range(5)]
        for key in themes.ORDER:
            theme = themes.THEMES[key]
            renders = {
                "stats": lambda: render_stats(_stats(), theme=theme),
                "rows": lambda: render_rows("TOP", "sub", rows, theme=theme),
                "albums": lambda: render_album_grid("TOP", "sub", albums, [], theme),
                "versus": lambda: render_versus("a", "b", "sub", metrics, theme=theme),
                "collage": lambda: build_collage(infos, theme=theme),
            }
            for name, render in renders.items():
                with self.subTest(theme=key, image=name):
                    with Image.open(render()) as image:
                        image.load()
                        self.assertGreater(image.width, 0)


if __name__ == "__main__":
    unittest.main()
