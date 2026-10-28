"""Stream a themed collage to FFmpeg; concatenate clips without audio crossfade."""
import asyncio
from dataclasses import dataclass
import colorsys
import io
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from bot.fonts import font, symbol_font, BOLD, EXTRABOLD, SEMIBOLD
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
    """Square music-player frames: blurred cover backdrop, pulsing cover, EQ row, progress, queue strip."""
    SOLO=dict(cover=420,top=52,title=496,title_px=34,artist_px=24,eq=606,eq_h=30,bar=654)
    GROUP=dict(cover=340,top=44,title=404,title_px=28,artist_px=20,eq=510,eq_h=26,bar=562)
    LIGHT=(255,255,255); SOFT=(206,206,218)

    def __init__(self, items, theme, size=720):
        self.items=items; self.count=len(items); self.theme=theme
        self.width=self.height=size; self.u=size/720
        self.layout=self.SOLO if self.count==1 else self.GROUP
        self.thumb=self._s(52)
        self.thumbs=[self._square(self._cover(item),self.thumb) for item in items]
        self._cached=None

    def _s(self, value): return max(1,round(value*self.u))

    def _cover(self, item):
        if item.cover_bytes:
            try:
                with Image.open(io.BytesIO(item.cover_bytes)) as image:
                    image=image.convert('RGB')
                    side=min(image.size); left=(image.width-side)//2; top=(image.height-side)//2
                    return image.crop((left,top,left+side,top+side))
            except Exception:
                pass
        placeholder=Image.new('RGB',(256,256),self.theme.card)
        ImageDraw.Draw(placeholder).text((128,128),'♪',font=symbol_font(120),fill=self.theme.muted,anchor='mm')
        return placeholder

    @staticmethod
    def _square(image, side): return image.resize((side,side),Image.Resampling.LANCZOS)

    @staticmethod
    def _rounded(image, radius):
        image=image.convert('RGBA'); big=image.width*4
        mask=Image.new('L',(big,big),0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,big-1,big-1),radius=radius*4,fill=255)
        image.putalpha(mask.resize(image.size,Image.Resampling.LANCZOS))
        return image

    def _accent(self, cover):
        if self.theme.palette: return self.theme.palette[0]
        h,sat,v=colorsys.rgb_to_hsv(*(c/255 for c in cover.resize((1,1),Image.Resampling.BOX).getpixel((0,0))))
        return tuple(round(c*255) for c in colorsys.hsv_to_rgb(h,max(sat,.45),max(v,.85)))

    @staticmethod
    def _fit(text, size, weight, width):
        for step in range(5):
            f=font(max(8,round(size*(1-.07*step))),weight)
            if f.getlength(text)<=width: return text,f
        while len(text)>1 and f.getlength(text+'…')>width: text=text[:-1]
        return text.rstrip()+'…',f

    def _static(self, index):
        if self._cached and self._cached[0]==index: return self._cached[1:]
        S=self.width; L=self.layout; item=self.items[index]
        cover=self._cover(item); accent=self._accent(cover)
        # Backdrop: heavily blurred cover, tinted by the accent, darker towards the text area.
        bg=cover.resize((32,32),Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(3)).resize((S,S),Image.Resampling.BICUBIC)
        bg=ImageEnhance.Brightness(ImageEnhance.Color(bg).enhance(1.25)).enhance(.42)
        bg=Image.blend(bg,Image.new('RGB',(S,S),accent),.10)
        ramp=1-.3*np.clip((np.arange(S)-S/2)/(S/2),0,1)
        bg=Image.fromarray((np.asarray(bg,dtype=np.float32)*ramp[:,None,None]).astype(np.uint8))
        canvas=bg.convert('RGBA')
        cs=self._s(L['cover']); cx=(S-cs)//2; cy=self._s(L['top']); radius=round(cs*.06)
        # Soft drop shadow under the cover.
        shadow=Image.new('L',(S,S),0)
        ImageDraw.Draw(shadow).rounded_rectangle((cx,cy+self._s(16),cx+cs,cy+cs+self._s(16)),radius=radius,fill=150)
        canvas.paste((0,0,0,255),mask=shadow.filter(ImageFilter.GaussianBlur(self._s(22))))
        card=self._square(cover,cs)
        # Listener chip lives on the cover so it pulses with it.
        name,f=self._fit(item.tg_name,16,BOLD,cs*.6)
        px=self._s(12); py=self._s(8); dot=self._s(8)
        chip_w=round(f.getlength(name))+2*px+dot+self._s(8); chip_h=f.size+2*py
        chip=Image.new('RGBA',card.size); overlay=ImageDraw.Draw(chip)
        x0=y0=self._s(14)
        overlay.rounded_rectangle((x0,y0,x0+chip_w,y0+chip_h),radius=chip_h//2,fill=(0,0,0,150))
        overlay.ellipse((x0+px,y0+(chip_h-dot)//2,x0+px+dot,y0+(chip_h+dot)//2),fill=accent)
        overlay.text((x0+px+dot+self._s(8),y0+chip_h//2),name,font=f,fill=self.LIGHT,anchor='lm')
        card=Image.alpha_composite(card.convert('RGBA'),chip)
        draw=ImageDraw.Draw(canvas)
        label='LADSJAM'; lf=font(self._s(13),BOLD); gap=self._s(4)
        total=sum(lf.getlength(c)+gap for c in label)-gap; lx=(S-total)/2
        for c in label:
            draw.text((lx,self._s(18)),c,font=lf,fill=self.SOFT); lx+=lf.getlength(c)+gap
        margin=S-2*self._s(48)
        title,tf=self._fit(item.track,self._s(L['title_px']),EXTRABOLD,margin)
        artist,af=self._fit(item.artist,self._s(L['artist_px']),SEMIBOLD,margin)
        ty=self._s(L['title']); draw.text((S/2,ty),title,font=tf,fill=self.LIGHT,anchor='mt')
        draw.text((S/2,ty+tf.size+self._s(8)),artist,font=af,fill=accent,anchor='mt')
        by=self._s(L['bar']); lo=self._s(60)
        overlay=Image.new('RGBA',(S,S),(0,0,0,0))
        ImageDraw.Draw(overlay).rounded_rectangle((lo,by,S-lo,by+self._s(6)),radius=self._s(3),fill=(255,255,255,60))
        if self.count>1: self._strip(overlay,index,accent)
        canvas=Image.alpha_composite(canvas,overlay).convert('RGB')
        self._cached=(index,canvas,self._rounded(card,radius),accent)
        return self._cached[1:]

    def _strip(self, overlay, index, accent):
        # Queue strip: a window of covers around the active one; the others stay dimmed.
        S=self.width; n=min(self.count,9); start=min(max(index-n//2,0),self.count-n)
        t=self.thumb; gap=self._s(10); x=(S-(n*t+(n-1)*gap))//2; y=self._s(620)
        draw=ImageDraw.Draw(overlay)
        for i in range(start,start+n):
            image=self.thumbs[i]
            if i!=index: image=ImageEnhance.Brightness(image).enhance(.45)
            overlay.paste(self._rounded(image,self._s(10)),(x,y))
            if i==index: draw.rounded_rectangle((x-3,y-3,x+t+2,y+t+2),radius=self._s(12),outline=accent,width=3)
            x+=t+gap

    def _shapes(self, canvas, box, fill, draw, ss=4):
        """Antialiased shapes: draw into a supersampled mask for the box, then paste the colour through it."""
        x0,y0,x1,y1=box
        mask=Image.new('L',((x1-x0)*ss,(y1-y0)*ss),0)
        draw(ImageDraw.Draw(mask),lambda x,y:((x-x0)*ss,(y-y0)*ss),ss)
        canvas.paste(fill,box,mask.resize((x1-x0,y1-y0),Image.Resampling.BOX))

    def frame(self, index, t, seconds, bars):
        base,card,accent=self._static(index)
        S=self.width; L=self.layout
        canvas=base.copy()
        cs=card.width; cx=(S-cs)//2; cy=self._s(L['top'])
        # The cover breathes with the active clip's audio; it never leaves its own frame.
        w=round(cs*(1+.025*float(np.mean(bars))))
        pulsed=card.resize((w,w),Image.Resampling.BICUBIC)
        canvas.paste(pulsed,(cx-(w-cs)//2,cy-(w-cs)//2),pulsed)
        count=len(bars); bw=self._s(12); gap=self._s(8); x0=(S-(count*bw+(count-1)*gap))//2
        mid=self._s(L['eq']); half=self._s(L['eq_h'])
        def sticks(draw,pt,ss):
            for j,value in enumerate(bars):
                h=max(self._s(3),float(value)*half); x=x0+j*(bw+gap)
                draw.rounded_rectangle((*pt(x,mid-h),*pt(x+bw,mid+h)),radius=bw*ss/2,fill=255)
        self._shapes(canvas,(x0-2,mid-half-3,x0+count*(bw+gap)+2,mid+half+4),accent,sticks)
        by=self._s(L['bar']); lo=self._s(60); span=S-2*lo; done=min(1,(t+1/24)/seconds)
        end=lo+max(self._s(6),span*done); knob=self._s(7); thick=self._s(6)
        box=(lo-2,by+thick//2-knob-2,S-lo+knob+2,by+thick//2+knob+3)
        self._shapes(canvas,box,accent,lambda draw,pt,ss:draw.rounded_rectangle((*pt(lo,by),*pt(end,by+thick)),radius=thick*ss/2,fill=255))
        self._shapes(canvas,box,self.LIGHT,lambda draw,pt,ss:draw.ellipse((*pt(end-knob,by+thick/2-knob),*pt(end+knob,by+thick/2+knob)),fill=255))
        draw=ImageDraw.Draw(canvas)
        tf=font(self._s(15),BOLD); elapsed=min(seconds,int(t)); ty=by+self._s(16)
        draw.text((lo,ty),f'{elapsed//60}:{elapsed%60:02d}',font=tf,fill=self.SOFT)
        left=seconds-elapsed
        draw.text((S-lo,ty),f'-{left//60}:{left%60:02d}',font=tf,fill=self.SOFT,anchor='ra')
        return canvas

    def motion(self, index, t, seconds, previous, bars, fps, samples=4):
        """Motion-blurred frame: average sub-frames across a 180-degree shutter."""
        previous=np.asarray(previous,dtype=np.float32); bars=np.asarray(bars,dtype=np.float32)
        total=None
        for k in range(samples):
            a=(k+1)/samples
            image=self.frame(index,t-.5*(1-a)/fps,seconds,previous+(bars-previous)*a)
            data=np.asarray(image,dtype=np.float32)
            total=data if total is None else total+data
        return Image.fromarray((total/samples+.5).astype(np.uint8))


class BarSmoother:
    """Fast attack, slow release so sticks glide instead of flickering."""
    def __init__(self, fps, count=16, attack=.025, release=.11):
        self.value=np.zeros(count,dtype=np.float32)
        self.up=1-math.exp(-1/(fps*attack)); self.down=1-math.exp(-1/(fps*release))

    def step(self, raw):
        rate=np.where(raw>self.value,self.up,self.down)
        self.value=self.value+(raw-self.value)*rate
        return self.value


def audio_bars(waveform,t):
    position=int(t*16000)
    data=waveform[position:position+1024]
    if len(data)<16: return np.zeros(16)
    spectrum=abs(np.fft.rfft(data*np.hanning(len(data))))
    edges=np.unique(np.geomspace(1,len(spectrum),17).astype(int))
    values=[float(np.sqrt(np.mean(spectrum[a:b]**2))) for a,b in zip(edges[:-1],edges[1:])]
    values=np.pad(values,(0,16-len(values)))
    return np.clip(np.log1p(values)*.45,0,1)


async def render_segment(frames,segment,path,ffmpeg,fps=60):
    seconds=segment.seconds
    args=[ffmpeg,'-v','error','-y','-threads','1','-filter_threads','1',
          '-f','rawvideo','-pix_fmt','rgb24','-s',f'{frames.width}x{frames.height}','-r',str(fps),'-i','pipe:0',
          '-ss',str(segment.start),'-i',str(segment.audio),'-map','0:v:0','-map','1:a:0',
          '-t',str(seconds),'-c:v','libx264','-preset','veryfast','-crf','20','-threads','1',
          '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-ar','48000','-ac','2',
          '-af',f'atrim=duration={seconds},asetpts=PTS-STARTPTS,apad,atrim=duration={seconds},loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.04,afade=t=out:st={seconds-.08}:d=0.08',
          '-movflags','+faststart',str(path)]
    process=await spawn(*args,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
    errors=asyncio.create_task(read_bounded(process.stderr))
    async def feed():
        smoother=BarSmoother(fps); previous=smoother.value.copy()
        for frame in range(seconds*fps):
            t=frame/fps
            bars=smoother.step(audio_bars(segment.waveform,t)).copy()
            image=await in_thread(frames.motion,segment.index,t,seconds,previous,bars,fps)
            previous=bars
            process.stdin.write(image.tobytes())
            await process.stdin.drain()
        process.stdin.close()
        await process.wait()
        await errors
        if process.returncode: raise MediaError('FFmpeg could not encode canvas')
    try:
        await asyncio.wait_for(feed(),timeout=max(120,seconds*20))
    except (BrokenPipeError,ConnectionResetError) as exc:
        raise MediaError('FFmpeg stopped accepting frames') from exc
    finally:
        await stop(process)
        if not errors.done(): errors.cancel()
        await asyncio.gather(errors,return_exceptions=True)


async def render_movie(items,segments,directory,theme,ffmpeg,size=720,fps=60):
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
