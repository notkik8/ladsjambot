"""Video version of the listening report, sharing Canvas audio selection."""
import asyncio
import logging
import re
import shutil
import tempfile
from pathlib import Path

from aiogram.filters import Filter
from aiogram.types import FSInputFile, Message

from bot import stats as st
from bot.canvas.analysis import analyse_audio
from bot.canvas.process import MediaError, in_thread, run
from bot.canvas.render import join_segments
from bot.canvas.resolver import resolve_audio
from bot.canvas.service import CanvasBusy, CanvasService, track_seconds
from bot.database import Database
from bot.handlers.stats import API_ERROR, _hero_covers, _parse_days, _self_user, router
from bot.infographic import render_stats
from bot.lastfm import LastFMClient, TrackInfo
from bot.themes import for_chat

log = logging.getLogger(__name__)


class VidStatsCommand(Filter):
    async def __call__(self, message: Message):
        match = re.fullmatch(r'(?i)(/?)vidstats(?:@([A-Za-z0-9_]+))?(?:\s+(.*))?', (message.text or '').strip())
        if not match or (match[2] and not match[1]):
            return False
        if match[2]:
            me = await message.bot.me()
            if match[2].casefold() != (me.username or '').casefold():
                return False
        return {'vidstats_args': (match[3] or '').lower().split()}


@router.message(VidStatsCommand())
async def cmd_vidstats(message: Message, vidstats_args: list[str], db: Database,
                       lastfm: LastFMClient, canvas_service: CanvasService):
    user = await _self_user(message, db)
    if not user:
        return
    days = _parse_days(vidstats_args, default=7, maximum=30)
    wait = None
    try:
        async with canvas_service.admit(message.chat.id):
            async with asyncio.timeout(900):
                wait = await message.reply('Собираю видео со статистикой и треками…')
                scrobbles, truncated = await st.fetch_scrobbles(lastfm, user['lastfm_user'], st.since_days(days))
                if scrobbles is None:
                    await message.answer(API_ERROR)
                    return
                if not scrobbles:
                    await message.answer(f'За последние {days} дн. количество прослушиваний — 0 🤷')
                    return
                data = st.build_stats(user['tg_name'], days, scrobbles, truncated)
                covers = await _hero_covers(lastfm, user['lastfm_user'], '7day' if days <= 7 else '1month')
                theme = await for_chat(db, message.chat.id)
                await in_thread(canvas_service.analyser._load)
                with tempfile.TemporaryDirectory(prefix='ladsjam-vidstats-', dir=canvas_service.temp_dir) as folder:
                    root = Path(folder)
                    clips = root / 'clips'
                    clips.mkdir()
                    parts, skipped = [], []
                    for i, (track, artist, _count) in enumerate(data.top_tracks):
                        directory = root / f'audio-{i:03d}'
                        directory.mkdir()
                        clip = clips / f'segment-{i:03d}.mp4'
                        try:
                            async with asyncio.timeout(150):
                                item = TrackInfo(message.from_user.id, user['tg_name'], user['lastfm_user'], artist, track)
                                duration = await track_seconds(lastfm, item)
                                audio = await resolve_audio(artist, track, directory / 'download', duration)
                                start, pcm = await analyse_audio(audio.path, directory, canvas_service.analyser,
                                                                 canvas_service.ffmpeg, 7, preview=getattr(audio, 'preview', False))
                                del pcm
                            image = directory / 'report.jpg'
                            rendered = await in_thread(render_stats, data, covers, theme, i)
                            image.write_bytes(rendered.getvalue())
                            del rendered
                            await run([canvas_service.ffmpeg, '-v', 'error', '-nostdin', '-y',
                                           '-loop', '1', '-framerate', '25', '-i', image,
                                           '-ss', str(start), '-i', audio.path, '-t', '7',
                                           '-map', '0:v:0', '-map', '1:a:0',
                                           '-vf', 'scale=720:-2', '-c:v', 'libx264', '-preset', 'veryfast',
                                           '-crf', '20', '-threads', '2', '-pix_fmt', 'yuv420p',
                                           '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2',
                                           '-af', 'atrim=duration=7,asetpts=PTS-STARTPTS,apad,atrim=duration=7,loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.04,afade=t=out:st=6.92:d=0.08',
                                           '-movflags', '+faststart', clip], timeout=140, watch_dir=clips)
                            parts.append(clip)
                        except (MediaError, TimeoutError, ValueError, OSError) as exc:
                            log.warning('Vidstats track %s skipped (%s)', i + 1, type(exc).__name__)
                            clip.unlink(missing_ok=True)
                            skipped.append(i + 1)
                        finally:
                            shutil.rmtree(directory, ignore_errors=True)
                    if not parts:
                        raise MediaError('No audio found for any top track')
                    output = await join_segments(parts, clips, canvas_service.ffmpeg)
                    await message.reply_video(video=FSInputFile(output), duration=7 * len(parts),
                                              supports_streaming=True, request_timeout=120)
                    if skipped:
                        await message.reply('Аудио не найдено для строк: ' + ', '.join(map(str, skipped)) + '.')
    except CanvasBusy:
        await message.reply('Канвас уже готовится или очередь заполнена. Попробуй чуть позже.')
    except (MediaError, TimeoutError, OSError) as exc:
        log.warning('Vidstats request failed (%s)', type(exc).__name__)
        await message.reply('Не удалось собрать видео: подходящее аудио недоступно или обработка не завершилась. Попробуй позже.')
    finally:
        if wait:
            try:
                await wait.delete()
            except Exception:
                pass
