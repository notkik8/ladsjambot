import unittest
import numpy as np
from bot.canvas.resolver import deezer_candidates, itunes_candidates, preview_url, rank_candidate
from bot.canvas.analysis import Features, choose_excerpt


class MatchingTests(unittest.TestCase):
    def test_artist_words_shared_with_title_and_soundcloud_raw_track(self):
        self.assertGreater(rank_candidate('The Weeknd','The Hills',{'title':'The Weeknd - The Hills (Official Audio)','duration':240}),.8)
        self.assertGreater(rank_candidate('Daft Punk','Get Lucky',{'title':'Daft Punk - Get Lucky','track':'Daft Punk - Get Lucky','duration':248}),.8)

    def test_credited_producer_and_featured_artist(self):
        self.assertGreater(rank_candidate('ROCKET','инкассатор',{'title':'ROCKET − Инкассатор (prod. by FRESCO)','duration':150}),.8)
        self.assertGreater(rank_candidate('LILDRUGHILL','терминал',{'title':'Терминал (feat. ROCKET)','channel':'LILDRUGHILL','duration':162}),.8)
        self.assertGreater(rank_candidate('Freddie Gibbs','Feeling',{'title':'Freddie Gibbs & The Alchemist - "Feeling (feat. Larry June)" (Official Visualizer)','duration':236}),.8)
        self.assertEqual(rank_candidate('ROCKET','инкассатор',{'title':'ROCKET − Инкассатор (remix) (prod. by FRESCO)','duration':150}),0)

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


class PreviewTests(unittest.TestCase):
    def test_deezer_and_itunes_entries_rank_like_other_sources(self):
        deezer={'data':[{'title':'Blinding Lights','artist':{'name':'The Weeknd'},'duration':200,
                         'preview':'https://cdnt-preview.dzcdn.net/api/1/1/a/b/c/0/x.mp3','link':'https://www.deezer.com/track/1'},
                        {'title':'Blinding Lights (Remix)','artist':{'name':'The Weeknd'},'duration':210,'preview':'https://cdnt-preview.dzcdn.net/r.mp3'},
                        {'title':'No preview','artist':{'name':'The Weeknd'},'duration':200,'preview':''}]}
        rows=list(deezer_candidates(deezer))
        self.assertEqual(len(rows),2)
        self.assertGreaterEqual(rank_candidate('The Weeknd','Blinding Lights',rows[0][0],200),.8)
        self.assertEqual(rank_candidate('The Weeknd','Blinding Lights',rows[1][0],200),0)
        itunes={'results':[{'trackName':'Космос','artistName':'Скриптонит','trackTimeMillis':180000,
                            'previewUrl':'https://audio-ssl.itunes.apple.com/p.m4a','trackViewUrl':'https://music.apple.com/x'}]}
        meta,url,link,source=next(itunes_candidates(itunes))
        self.assertEqual((meta['duration'],source),(180,'Apple Music'))
        self.assertGreaterEqual(rank_candidate('Скриптонит','Космос',meta),.8)

    def test_only_https_store_preview_hosts(self):
        self.assertTrue(preview_url('https://cdnt-preview.dzcdn.net/a.mp3'))
        self.assertTrue(preview_url('https://audio-ssl.itunes.apple.com/a.m4a'))
        for bad in ('http://cdnt-preview.dzcdn.net/a.mp3','https://evil.example/dzcdn.net','https://dzcdn.net.evil.example/a','https://u@cdnt-preview.dzcdn.net/a'):
            self.assertFalse(preview_url(bad),bad)

    def test_preview_excerpt_may_start_at_the_hook(self):
        energy=np.ones(28); vocals=np.zeros(28); vocals[:15]=.9
        features=Features(energy,vocals,np.zeros(28),np.zeros(28),28)
        self.assertEqual(choose_excerpt(features,15,edges=False),0)
