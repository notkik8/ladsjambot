import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from html import escape, unescape
import logging
from pathlib import Path
import re
import shutil
import tempfile
import time

from aiogram.types import FSInputFile
from .analysis import Analyser, analyse_audio
from .process import MediaError, in_thread
from .render import CanvasFrames, Segment, join_segments, render_segment
from .resolver import resolve_audio

log=logging.getLogger(__name__)


class CanvasBusy(MediaError): pass


# Everyone shares one video; a new one starts only near Telegram's 50 MB bot upload limit.
PART_BYTES=40*1024*1024
CAPTION_LIMIT=1024; MESSAGE_LIMIT=4096


def visible(text):
    return len(unescape(re.sub(r'<[^>]+>','',text)))


def chunks(lines, limit):
    block=[]
    for line in lines:
        if block and visible('\n'.join(block+[line]))>limit:
            yield '\n'.join(block); block=[]
        block.append(line)
    if block: yield '\n'.join(block)


async def track_seconds(lastfm,item):
    try:
        info=await lastfm.call('track.getInfo',retries=0,artist=item.artist,track=item.track)
        return float((info or {}).get('track',{}).get('duration',0))/1000 or None
    except (ValueError,TypeError,AttributeError):
        return None


class CanvasService:
    def __init__(self, model_path=Path('.cache/canvas_models/yamnet.tflite'),ffmpeg='ffmpeg',temp_dir=None):
        self.analyser=Analyser(Path(model_path)); self.ffmpeg=ffmpeg; self.temp_dir=temp_dir
        self.lock=asyncio.Lock(); self.chats=set(); self.tasks=set(); self.cache=OrderedDict()

    @asynccontextmanager
    async def admit(self, chat_id):
        if chat_id in self.chats or len(self.chats)>=3:
            raise CanvasBusy('Queue is full')
        self.chats.add(chat_id); task=asyncio.current_task(); self.tasks.add(task)
        acquired=False
        try:
            await asyncio.wait_for(self.lock.acquire(),timeout=900)
            acquired=True
            yield
        finally:
            if acquired: self.lock.release()
            self.chats.discard(chat_id); self.tasks.discard(task)

    async def close(self):
        tasks=[task for task in self.tasks if task is not asyncio.current_task()]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)

    def _key(self,items,theme,solo):
        return (3,solo,theme.key,tuple((t.tg_id,t.tg_name,t.artist,t.track) for t in items))

    async def send(self,message,items,theme,*,solo,lastfm):
        if not items: raise MediaError('No tracks')
        if len(items)>64: raise MediaError('Too many canvas participants (maximum 64)')
        key=self._key(items,theme,solo)
        cached=self.cache.get(key)
        if cached and time.monotonic()-cached[0]<cached[2]:
            self.cache.move_to_end(key)
            try:
                for kind,entry in cached[1]:
                    if kind=='video': await message.reply_video(**entry,parse_mode='HTML',supports_streaming=True,request_timeout=120)
                    else: await message.reply(entry,parse_mode='HTML')
                return
            except Exception:
                self.cache.pop(key,None)
                raise
        self.cache.pop(key,None)
        await in_thread(self.analyser._load)
        seconds=15 if solo else 6
        saved=[]; skipped=[]; part_number=0; replies=[]
        # The directory exists through the upload; all exits remove media and partial files.
        with tempfile.TemporaryDirectory(prefix='ladsjam-canvas-',dir=self.temp_dir) as folder:
            root=Path(folder)
            frames=await in_thread(CanvasFrames,items,theme)
            parts=[]; captions=[]; part_bytes=0
            async def flush():
                nonlocal part_number, parts, captions, part_bytes
                if not parts: return
                output_dir=root/f'part-{part_number}'
                output_dir.mkdir()
                # Concat manifest uses local fixed filenames.
                moved=[]
                for j,path in enumerate(parts):
                    destination=output_dir/f'segment-{j:03d}.mp4'
                    path.replace(destination); moved.append(destination)
                output=await join_segments(moved,output_dir,self.ffmpeg)
                caption='<b>LADSJAM · CANVAS</b>\n'+'\n'.join(captions)
                follow=[]
                if visible(caption)>CAPTION_LIMIT:
                    # A big group's track list goes right below the video instead of being cut off.
                    caption='<b>LADSJAM · CANVAS</b>\nСписок треков — в сообщении ниже.'
                    follow=list(chunks(captions,MESSAGE_LIMIT))
                entry=dict(caption=caption,width=frames.width,height=frames.height,duration=seconds*len(parts))
                sent=await message.reply_video(video=FSInputFile(output),**entry,parse_mode='HTML',supports_streaming=True,request_timeout=120)
                if sent.video: saved.append(('video',dict(entry,video=sent.video.file_id)))
                output.unlink(); output_dir.rmdir()
                for text in follow:
                    await message.reply(text,parse_mode='HTML'); saved.append(('text',text))
                part_number+=1; parts=[]; captions=[]; part_bytes=0
            # Audio for every participant is fetched and analysed ahead (bounded), while clips encode in order.
            gate=asyncio.Semaphore(3)
            async def prepare(i,item):
                async with gate:
                    directory=root/f'audio-{i:03d}'; directory.mkdir()
                    try:
                        async with asyncio.timeout(150):
                            duration=await track_seconds(lastfm,item)
                            audio=await resolve_audio(item.artist,item.track,directory/'download',duration)
                            start,pcm=await analyse_audio(audio.path,directory,self.analyser,self.ffmpeg,seconds,preview=getattr(audio,'preview',False))
                        return directory,audio,start,pcm
                    except BaseException:
                        shutil.rmtree(directory,ignore_errors=True); raise
            jobs=[asyncio.create_task(prepare(i,item)) for i,item in enumerate(items)]
            previous=-1
            try:
                for i,(item,job) in enumerate(zip(items,jobs)):
                    try:
                        directory,audio,start,pcm=await job
                        path=root/f'clip-{i:03d}.mp4'
                        # Start a new video before this clip if one more average clip would cross the upload budget.
                        if parts and part_bytes+1.5*part_bytes/len(parts)>PART_BYTES: await flush()
                        try:
                            # Clips in the same video slide in from the previous card; a new video opens fresh.
                            await render_segment(frames,Segment(i,audio.path,start,seconds,pcm,previous if parts else -1),path,self.ffmpeg)
                        finally:
                            shutil.rmtree(directory,ignore_errors=True); del pcm
                        parts.append(path); previous=i; part_bytes+=path.stat().st_size
                        name=escape(item.tg_name[:32]); title=escape(f'{item.artist} — {item.track}'[:70])
                        captions.append(f'{i+1}. {name}: {title}')
                    except (MediaError,TimeoutError,ValueError,OSError) as exc:
                        log.warning('Canvas track %s skipped (%s)',i,type(exc).__name__)
                        (root/f'clip-{i:03d}.mp4').unlink(missing_ok=True)
                        skipped.append(item.tg_name)
            finally:
                for job in jobs: job.cancel()
                await asyncio.gather(*jobs,return_exceptions=True)
            await flush()
            if not any(kind=='video' for kind,_ in saved): raise MediaError('No confident audio found for any track')
        if skipped:
            notice='Аудио не найдено: '+escape(', '.join(skipped)[:700])+'. Карточки оставлены, их очередь пропущена.'
            await message.reply(notice,parse_mode='HTML'); saved.append(('text',notice))
        self.cache[key]=(time.monotonic(),saved,120 if skipped else 3600)
        while len(self.cache)>128: self.cache.popitem(last=False)
