import unittest
import numpy as np
from bot.canvas.resolver import rank_candidate
from bot.canvas.analysis import Features, choose_excerpt


class MatchingTests(unittest.TestCase):
    def test_official_song_beats_cover_and_remix(self):
        good = {'title': 'Artist - My Song (Official Audio)', 'uploader': 'Artist - Topic', 'duration': 180}
        self.assertGreater(rank_candidate('Artist', 'My Song', good, 180), .8)
        for version in ('slowed', 'remix', 'live', 'cover', 'instrumental', 'karaoke'):
            bad = dict(good, title=f'Artist - My Song ({version})')
            self.assertEqual(rank_candidate('Artist', 'My Song', bad, 180), 0)

    def test_wrong_song_artist_duration_rejected(self):
        self.assertEqual(rank_candidate('Alice', 'Night Drive', {'title':'Bob - Night Drive', 'duration':180}, 180), 0)
        self.assertEqual(rank_candidate('Alice', 'Night Drive', {'title':'Alice - Daylight', 'duration':180}, 180), 0)
        self.assertEqual(rank_candidate('Alice', 'Night Drive', {'title':'Alice - Night Drive', 'duration':300}, 180), 0)

    def test_requested_remix_allowed(self):
        self.assertGreater(rank_candidate('Alice', 'Night Drive (Remix)', {'title':'Alice - Night Drive Remix', 'duration':180}), .8)


class ExcerptTests(unittest.TestCase):
    def test_vocal_section_preferred_over_loud_intro(self):
        energy=np.ones(90); energy[:20]=3
        voice=np.zeros(90); voice[35:60]=.9
        features=Features(energy, voice, np.zeros(90), np.zeros(90), 90)
        start=choose_excerpt(features, 15)
        self.assertGreaterEqual(start, 35)
        self.assertLessEqual(start+15, 60)

    def test_instrumental_uses_repeated_active_section(self):
        energy=np.ones(90); energy[:10]=0; energy[80:]=0
        repeats=np.zeros(90); repeats[35:60]=1
        start=choose_excerpt(Features(energy,np.zeros(90),repeats,np.zeros(90),90),15)
        self.assertGreaterEqual(start,35)
        self.assertLessEqual(start+15,60)

    def test_silence_and_too_short_fail(self):
        for length in (10, 90):
            with self.assertRaises(ValueError):
                choose_excerpt(Features(np.zeros(length),np.zeros(length),np.zeros(length),np.zeros(length),length),15)

    def test_partial_duration_does_not_overrun(self):
        f=Features(np.ones(16),np.zeros(16),np.zeros(16),np.zeros(16),15.3)
        self.assertLessEqual(choose_excerpt(f,15)+15,15.3)
