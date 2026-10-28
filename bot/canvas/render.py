"""Stream a themed collage to FFmpeg; concatenate clips without audio crossfade."""
import asyncio
from dataclasses import dataclass
import io
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

from bot.collage import build_collage
from bot.fonts import font, BOLD
from .process import MediaError, in_thread, read_bounded, run, spawn, stop


@dataclass
class Segment:
    index: int
    audio: Path
    start: float
    seconds: int
    waveform: np.ndarray


@dataclass
class Movie:
    path: Path
    width: int
    height: int
    duration: int


class CanvasFrames:
    def __init__(self, items, theme, size=720):
        self.items=items; self.count=len(items); self.theme=theme
        self.cols=math.ceil(math.sqrt(self.count))
        self.cell=max(40,(size//self.cols)//2*2)
        with Image.open(build_collage(items,cell_size=self.cell,theme=theme)) as image:
            self.base=image.convert('RGB')
        self.dim=ImageEnhance.Brightness(self.base).enhance(.48)
        self.width=self.base.width; self.height=self.base.height+48
        self.accent=theme.palette[0] if theme.palette else (167,139,250)
        self.font=font(14,BOLD)

    def frame(self, index, t, seconds, bars):
        canvas=Image.new('RGB',(self.width,self.height),self.theme.bg)
        canvas.paste(self.dim,(0,0))
        x=(index%self.cols)*self.cell; y=(index//self.cols)*self.cell
        # Tiny pulse stays inside its own cell, never hides a neighbour.
        card=self.base.crop((x,y,x+self.cell,y+self.cell))
        amount=1+.012*float(np.mean(bars))
        expanded=card.resize((round(self.cell*amount),round(self.cell*amount)),Image.Resampling.BILINEAR)
        off=(expanded.width-self.cell)//2
        canvas.paste(expanded.crop((off,off,off+self.cell,off+self.cell)),(x,y))
        draw=ImageDraw.Draw(canvas)
        draw.rounded_rectangle((x+2,y+2,x+self.cell-3,y+self.cell-3),radius=max(3,self.cell//40),outline=self.accent,width=3)
        # Bars respond only to the active clip's PCM, never to other participants.
        bw=max(2,self.cell//80); gap=bw; count=len(bars)
        bx=x+(self.cell-count*(bw+gap))//2; by=y+max(22,self.cell//9)
        draw.rounded_rectangle((bx-6,y+8,bx+count*(bw+gap)+6,by+5),radius=5,fill=(16,13,25))
        for j,value in enumerate(bars):
            h=max(2,round(float(value)*max(8,self.cell//12)))
            draw.rectangle((bx+j*(bw+gap),by-h,bx+j*(bw+gap)+bw,by),fill=self.accent)
        footer=self.base.height
        label=f'LADSJAM / {index+1:02d} / {self.count:02d}'
        draw.text((12,footer+9),label,font=self.font,fill=self.theme.ink)
        duration=f'{min(seconds,int(t)+1):02d} / {seconds:02d}'
        draw.text((self.width-12-draw.textlength(duration,font=self.font),footer+9),duration,font=self.font,fill=self.theme.muted)
        draw.rectangle((0,self.height-4,max(1,int(self.width*min(1,(t+1/24)/seconds))),self.height-1),fill=self.accent)
        return canvas


def audio_bars(waveform,t):
    position=int(t*16000)
    data=waveform[position:position+1024]
    if len(data)<16: return np.zeros(16)
    spectrum=abs(np.fft.rfft(data*np.hanning(len(data))))
    edges=np.unique(np.geomspace(1,len(spectrum),17).astype(int))
    values=[float(np.sqrt(np.mean(spectrum[a:b]**2))) for a,b in zip(edges[:-1],edges[1:])]
    values=np.pad(values,(0,16-len(values)))
    return np.clip(np.log1p(values)*.45,0,1)


async def render_segment(frames,segment,path,ffmpeg,fps=24):
    seconds=segment.seconds
    args=[ffmpeg,'-v','error','-y','-threads','1','-filter_threads','1',
          '-f','rawvideo','-pix_fmt','rgb24','-s',f'{frames.width}x{frames.height}','-r',str(fps),'-i','pipe:0',
          '-ss',str(segment.start),'-i',str(segment.audio),'-map','0:v:0','-map','1:a:0',
          '-t',str(seconds),'-c:v','libx264','-preset','veryfast','-crf','24','-threads','1',
          '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-ar','48000','-ac','2',
          '-af',f'atrim=duration={seconds},asetpts=PTS-STARTPTS,apad,atrim=duration={seconds},loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.04,afade=t=out:st={seconds-.08}:d=0.08',
          '-movflags','+faststart',str(path)]
    process=await spawn(*args,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
    errors=asyncio.create_task(read_bounded(process.stderr))
    async def feed():
        for frame in range(seconds*fps):
            t=frame/fps
            image=frames.frame(segment.index,t,seconds,audio_bars(segment.waveform,t))
            process.stdin.write(image.tobytes())
            await process.stdin.drain()
        process.stdin.close()
        await process.wait()
        await errors
        if process.returncode: raise MediaError('FFmpeg could not encode canvas')
    try:
        await asyncio.wait_for(feed(),timeout=max(90,seconds*12))
    except (BrokenPipeError,ConnectionResetError) as exc:
        raise MediaError('FFmpeg stopped accepting frames') from exc
    finally:
        await stop(process)
        if not errors.done(): errors.cancel()
        await asyncio.gather(errors,return_exceptions=True)


async def render_movie(items,segments,directory,theme,ffmpeg,size=720,fps=24):
    if not segments: raise MediaError('No audio segments to render')
    directory.mkdir(parents=True,exist_ok=True)
    frames=await in_thread(CanvasFrames,items,theme,size)
    parts=[]
    for number,segment in enumerate(segments):
        path=directory/f'segment-{number:03d}.mp4'
        await render_segment(frames,segment,path,ffmpeg,fps)
        parts.append(path)
    output=await join_segments(parts,directory,ffmpeg)
    return Movie(output,frames.width,frames.height,sum(s.seconds for s in segments))


async def join_segments(parts,directory,ffmpeg):
    output=directory/'canvas.mp4'
    if len(parts)==1:
        parts[0].replace(output)
    else:
        manifest=directory/'concat.txt'
        # Fixed generated basenames avoid quoting and path injection in ffconcat.
        manifest.write_text(''.join(f"file '{path.name}'\n" for path in parts),encoding='utf-8')
        await run([ffmpeg,'-v','error','-nostdin','-y','-f','concat','-safe','1','-i',manifest,
                   '-c','copy','-movflags','+faststart',output],timeout=45)
        for path in parts: path.unlink()
        manifest.unlink()
    if output.stat().st_size>45*1024*1024:
        raise MediaError('Canvas exceeds Telegram upload budget')
    return output
