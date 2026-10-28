import json
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from .process import MediaError, run

VERSIONS={'remix','live','cover','karaoke','instrumental','slowed','sped','nightcore','reverb','acoustic','concert','tribute'}
NOISE={'official','audio','video','lyrics','lyric','hd','hq','visualizer','mv','music','topic'}


def words(value):
    return re.findall(r'\w+', unicodedata.normalize('NFKC', str(value or '')).casefold())


def rank_candidate(artist, title, candidate, duration=None):
    """Conservatively match the recording; never select merely the first result."""
    if candidate.get('is_live') or candidate.get('live_status') == 'is_live': return 0.
    seconds=candidate.get('duration')
    if not isinstance(seconds,(int,float)) or not 15 <= seconds <= 600: return 0.
    a=set(words(artist)); t=set(words(title))
    raw=set(words(candidate.get('title')))
    if (raw & VERSIONS) != (t & VERSIONS): return 0.
    identity=raw | set(words(candidate.get('artist'))) | set(words(candidate.get('uploader'))) | set(words(candidate.get('channel')))
    if not a or len(a & identity)/len(a) < .8: return 0.
    wanted=t-NOISE or t
    found_raw=set(words(candidate.get('track'))) or raw
    # SoundCloud's track can contain the whole upload title. Preserve words
    # shared by the artist and song, e.g. The Weeknd / The Hills.
    found=found_raw-(a-wanted)-(NOISE-wanted)
    recall=len(wanted & found)/max(1,len(wanted))
    similarity=SequenceMatcher(None,' '.join(sorted(wanted)),' '.join(sorted(found))).ratio()
    if recall < .85 or similarity < .65: return 0.
    duration_score=.5
    if duration and duration > 0:
        delta=abs(seconds-duration)
        if delta > max(8,duration*.07): return 0.
        duration_score=max(0,1-delta/max(8,duration*.07))
    return .65*similarity + .25*len(a & identity)/len(a) + .1*duration_score


def allowed_url(value):
    try:
        parsed=urlparse(value)
        host=(parsed.hostname or '').lower()
        return parsed.scheme == 'https' and not parsed.username and parsed.port in (None,443) and (
            host in {'youtube.com','www.youtube.com','music.youtube.com','youtu.be','soundcloud.com','www.soundcloud.com'}
        )
    except (ValueError,TypeError): return False


@dataclass
class ResolvedAudio:
    path: Path
    url: str
    source: str


async def resolve_audio(artist, title, directory: Path, duration=None):
    directory.mkdir(parents=True,exist_ok=True)
    base=[sys.executable,'-m','yt_dlp','--ignore-config','--no-playlist','--no-warnings','--socket-timeout','12','--retries','1','--extractor-retries','1']
    if shutil.which('node'): base += ['--js-runtimes','node']
    candidates=[]
    # Sequential searches keep extractor memory bounded; both providers can fail independently.
    for prefix in ('ytsearch5:','scsearch5:'):
        try:
            data=await run(base+['--flat-playlist','--dump-single-json','--',f'{prefix}{artist} {title}'],timeout=35)
            entries=json.loads(data).get('entries') or []
            for entry in entries:
                if not isinstance(entry,dict): continue
                url=entry.get('webpage_url') or entry.get('url')
                if prefix.startswith('yt') and entry.get('id') and not allowed_url(url):
                    vid=str(entry['id'])
                    if re.fullmatch(r'[\w-]{11}',vid): url='https://www.youtube.com/watch?v='+vid
                score=rank_candidate(artist,title,entry,duration)
                if score >= .80 and allowed_url(url): candidates.append((score,url))
        except (MediaError,TimeoutError,ValueError):
            continue
    for _,url in sorted(set(candidates),reverse=True)[:3]:
        # Separate attempts avoid picking a partial file from a failed download.
        attempt=directory / str(len(list(directory.iterdir())))
        attempt.mkdir()
        try:
            await run(base+['-f','bestaudio[abr<=160]/bestaudio/best[height<=360]',
                           '--max-filesize','40M','--no-part','--no-mtime',
                           '-o',str(attempt/'audio.%(ext)s'),'--',url],timeout=100,watch_dir=attempt)
            files=[p for p in attempt.glob('audio.*') if p.is_file() and p.suffix not in {'.part','.ytdl'}]
            if len(files)==1 and 0 < files[0].stat().st_size <= 40*1024*1024:
                return ResolvedAudio(files[0],url,'SoundCloud' if 'soundcloud.com' in urlparse(url).netloc else 'YouTube')
        except (MediaError,TimeoutError):
            pass
        shutil.rmtree(attempt)
    raise MediaError('No confident downloadable match')
