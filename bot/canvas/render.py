"""Stream a themed collage to FFmpeg; concatenate clips without audio crossfade."""
import asyncio
from dataclasses import dataclass, replace
import colorsys
import io
import math
import os
from pathlib import Path
import threading
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
    came_from: int = -1  # previous card in the same video, -1 = the video opens on this clip


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
        self._statics={}; self._cards={}
        self._eq_geometry()

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
        if index in self._statics: return self._statics[index]
        S=self.width; L=self.layout; item=self.items[index]
        cover=self._cover(item); accent=self._accent(cover)
        # Backdrop: heavily blurred cover, tinted by the accent, darker towards the text area.
        bg=cover.resize((32,32),Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(3)).resize((S,S),Image.Resampling.BICUBIC)
        bg=ImageEnhance.Brightness(ImageEnhance.Color(bg).enhance(1.25)).enhance(.42)
        bg=Image.blend(bg,Image.new('RGB',(S,S),accent),.10)
        ramp=1-.3*np.clip((np.arange(S)-S/2)/(S/2),0,1)
        bg=Image.fromarray((np.asarray(bg,dtype=np.float32)*ramp[:,None,None]).astype(np.uint8))
        canvas=bg.convert('RGBA')
        cs=self._s(L['cover']); radius=round(cs*.06)
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
        # The soft drop shadow is part of the card so it slides with it in transitions.
        pad=self._s(48); full=Image.new('RGBA',(cs+2*pad,cs+2*pad),(0,0,0,0))
        shadow=Image.new('L',full.size,0)
        ImageDraw.Draw(shadow).rounded_rectangle((pad,pad+self._s(16),pad+cs,pad+cs+self._s(16)),radius=radius,fill=150)
        full.putalpha(shadow.filter(ImageFilter.GaussianBlur(self._s(22))))
        full.alpha_composite(self._rounded(card,radius),(pad,pad))
        draw=ImageDraw.Draw(canvas)
        label='LADSJAM'; lf=font(self._s(13),BOLD); gap=self._s(4)
        total=sum(lf.getlength(c)+gap for c in label)-gap; lx=(S-total)/2
        for c in label:
            draw.text((lx,self._s(18)),c,font=lf,fill=self.SOFT); lx+=lf.getlength(c)+gap
        margin=S-2*self._s(48)
        title,tf=self._fit(item.track,self._s(L['title_px']),EXTRABOLD,margin)
        artist,af=self._fit(item.artist,self._s(L['artist_px']),SEMIBOLD,margin)
        # Title and artist live on their own layer so transitions can move them separately.
        ty=self._s(L['title']); top=ty-self._s(8)
        words=Image.new('RGBA',(S,tf.size+af.size+self._s(28)),(0,0,0,0)); write=ImageDraw.Draw(words)
        write.text((S/2,ty-top),title,font=tf,fill=self.LIGHT,anchor='mt')
        write.text((S/2,ty-top+tf.size+self._s(8)),artist,font=af,fill=accent,anchor='mt')
        by=self._s(L['bar']); lo=self._s(60)
        overlay=Image.new('RGBA',(S,S),(0,0,0,0))
        ImageDraw.Draw(overlay).rounded_rectangle((lo,by,S-lo,by+self._s(6)),radius=self._s(3),fill=(255,255,255,60))
        if self.count>1: self._strip(overlay,index,accent)
        backdrop=Image.alpha_composite(canvas,overlay)
        base=backdrop.copy(); base.alpha_composite(words,(0,top))
        entry=self._statics[index]=(base.convert('RGB'),full,accent,backdrop.convert('RGB'),(words,top))
        # Only the current card and the one it came from are ever needed.
        while len(self._statics)>2: self._statics.pop(next(iter(self._statics)))
        self._cards={key:value for key,value in self._cards.items() if key[0] in self._statics}
        return entry

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

    def _eq_geometry(self):
        # Pixel-centre grids for the EQ row and progress bar; antialiasing is computed analytically from distances.
        S=self.width; L=self.layout; self.bw=self._s(12); gap=self._s(8); count=16
        x0=(S-(count*self.bw+(count-1)*gap))//2; self.mid=self._s(L['eq']); self.half=self._s(L['eq_h'])
        self.eq_box=(x0-2,self.mid-self.half-2,x0+count*(self.bw+gap)+2,self.mid+self.half+2)
        xs=np.arange(self.eq_box[0],self.eq_box[2])+.5
        centres=x0+np.arange(count)*(self.bw+gap)+self.bw/2
        self.eq_bar=np.clip(np.rint((xs-x0-self.bw/2)/(self.bw+gap)),0,count-1).astype(int)
        self.eq_dx=(xs-centres[self.eq_bar])[None,:]
        self.eq_dy=np.abs(np.arange(self.eq_box[1],self.eq_box[3])+.5-self.mid)[:,None]
        self.lo=self._s(60); self.by=self._s(L['bar']); self.thick=self._s(6); self.knob=self._s(7)
        cy=self.by+self.thick/2
        self.bar_box=(self.lo-self.knob-2,round(cy-self.knob)-2,S-self.lo+self.knob+2,round(cy+self.knob)+2)
        self.bar_x=(np.arange(self.bar_box[0],self.bar_box[2])+.5)[None,:]
        self.bar_y=(np.arange(self.bar_box[1],self.bar_box[3])+.5-cy)[:,None]

    @staticmethod
    def _mask(alpha):
        return Image.fromarray((np.clip(alpha,0,1)*255+.5).astype(np.uint8))

    def _eq_alpha(self, bars):
        r=self.bw/2
        # Each stick is a vertical capsule: distance to its core segment minus the radius.
        length=np.maximum(np.maximum(r,np.asarray(bars,dtype=np.float32)*self.half)-r,0)[self.eq_bar][None,:]
        dist=np.hypot(self.eq_dx,np.maximum(self.eq_dy-length,0))-r
        return np.clip(.5-dist,0,1)

    def _bar_alpha(self, t, seconds):
        r=self.thick/2; span=self.width-2*self.lo
        end=self.lo+max(self.thick,span*min(1,max(0,t+1/24)/seconds))
        dx=np.maximum(np.maximum(self.lo+r-self.bar_x,self.bar_x-(end-r)),0)
        fill=np.clip(.5-(np.hypot(dx,self.bar_y)-r),0,1)
        knob=np.clip(.5-(np.hypot(self.bar_x-end,self.bar_y)-self.knob),0,1)
        return fill,knob

    def _place(self, canvas, card, dx=0., dy=0., scale=1., alpha=1., key=None, fast=False):
        S=self.width; L=self.layout; w=max(2,round(card.width*scale))
        if key is not None and (key,w) in self._cards: image=self._cards[key,w]
        else:
            image=card.resize((w,w),Image.Resampling.BILINEAR if fast else Image.Resampling.BICUBIC)
            if key is not None: self._cards[key,w]=image
        if alpha<1:
            image=image.copy(); image.putalpha(image.getchannel('A').point(lambda v:round(v*alpha)))
        cs=self._s(L['cover']); centre=(S/2+dx,self._s(L['top'])+cs/2+dy)
        canvas.paste(image,(round(centre[0]-w/2),round(centre[1]-w/2)),image)

    def frame(self, index, t, seconds, bars, came_from=None):
        return self._render(index,seconds,[(t,np.asarray(bars,dtype=np.float32))],came_from)

    def motion(self, index, t, seconds, previous, bars, fps, samples=4, came_from=None):
        """Motion-blurred frame: moving shapes are averaged across a 180-degree shutter."""
        previous=np.asarray(previous,dtype=np.float32); bars=np.asarray(bars,dtype=np.float32)
        steps=[(k+1)/samples for k in range(samples)]
        return self._render(index,seconds,[(t-.5*(1-a)/fps,previous+(bars-previous)*a) for a in steps],came_from)

    TRANSITION=.6

    def _covers(self, canvas, index, came_from, p):
        S=self.width; card=self._static(index)[1]; ease=1-(1-p)**3
        if came_from>=0:
            # Carousel: the previous cover slides out left and shrinks, the new one glides in from the right.
            leave=p*p*(3-2*p); back=1+2.2*(p-1)**3+1.2*(p-1)**2
            self._place(canvas,self._static(came_from)[1],dx=-.62*S*leave,scale=1-.22*leave,alpha=1-leave,fast=True)
            self._place(canvas,card,dx=.62*S*(1-back),scale=.78+.22*ease,alpha=min(1.,p*2.2),fast=True)
        else:
            # Opening: the scene brightens while the cover rises into place.
            self._place(canvas,card,dy=self._s(36)*(1-ease),scale=.9+.1*ease,alpha=.35+.65*ease,fast=True)

    def _words(self, canvas, words, alpha, dy):
        layer,top=words
        if alpha<=0: return
        if alpha<1: layer=layer.copy(); layer.putalpha(layer.getchannel('A').point(lambda v:round(v*alpha)))
        canvas.paste(layer,(0,round(top+dy)),layer)

    def _render(self, index, seconds, samples, came_from=None):
        base,card,accent,backdrop,words=self._static(index)
        S=self.width; t=samples[-1][0]
        if came_from is not None and samples[0][0]<self.TRANSITION:
            p=min(1.,max(0.,t/self.TRANSITION)); ease=1-(1-p)**3
            # The backdrop crossfades from the previous card (or, opening a video, brightens from dark).
            old=self._static(came_from)[3] if came_from>=0 else Image.new('RGB',base.size,(0,0,0))
            backdrop=Image.blend(old,backdrop,ease if came_from>=0 else .4+.6*ease)
            # Old title lifts away first, the new one rises in behind it: never two titles on top of each other.
            if came_from>=0:
                out=min(1.,p/.4); self._words(backdrop,self._static(came_from)[4],1-out*out*(3-2*out),-self._s(14)*out)
            rise=min(1.,max(0.,(p-.4)/.6)); rise=1-(1-rise)**3
            self._words(backdrop,words,rise,self._s(18)*(1-rise))
            # Only the covers travel, so only they are averaged across the shutter.
            total=None
            for sample_t,_ in samples:
                layer=backdrop.copy(); self._covers(layer,index,came_from,min(1.,max(0.,sample_t/self.TRANSITION)))
                data=np.asarray(layer,dtype=np.uint16); total=data if total is None else total+data
            canvas=Image.fromarray(((total+len(samples)//2)//len(samples)).astype(np.uint8))
        else:
            canvas=base.copy(); ease=1.
            # The cover breathes with the active clip's audio; it never leaves its own frame.
            self._place(canvas,card,scale=1+.025*float(np.mean([np.mean(bars) for _,bars in samples])),key=index)
        eq=sum(self._eq_alpha(bars) for _,bars in samples)/len(samples)
        canvas.paste(accent,self.eq_box,self._mask(eq*ease))
        fill=knob=0
        for sample_t,_ in samples:
            f,k=self._bar_alpha(sample_t,seconds); fill=fill+f; knob=knob+k
        canvas.paste(accent,self.bar_box,self._mask(fill/len(samples)*ease))
        canvas.paste(self.LIGHT,self.bar_box,self._mask(knob/len(samples)*ease))
        draw=ImageDraw.Draw(canvas)
        tf=font(self._s(15),BOLD); elapsed=min(seconds,max(0,int(t))); ty=self.by+self._s(16)
        draw.text((self.lo,ty),f'{elapsed//60}:{elapsed%60:02d}',font=tf,fill=self.SOFT)
        left=seconds-elapsed
        draw.text((S-self.lo,ty),f'-{left//60}:{left%60:02d}',font=tf,fill=self.SOFT,anchor='ra')
        return canvas


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
          '-t',str(seconds),'-c:v','libx264','-preset','veryfast','-crf','20','-threads','2',
          '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-ar','48000','-ac','2',
          '-af',f'atrim=duration={seconds},asetpts=PTS-STARTPTS,apad,atrim=duration={seconds},loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.04,afade=t=out:st={seconds-.08}:d=0.08',
          '-movflags','+faststart',str(path)]
    read_fd,write_fd=os.pipe()
    try:
        process=await spawn(*args,stdin=read_fd,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
    except BaseException:
        os.close(write_fd); raise
    finally:
        os.close(read_fd)
    pipe=open(write_fd,'wb')
    errors=asyncio.create_task(read_bounded(process.stderr))
    halt=threading.Event()
    def produce():
        # Drawing and writing stay in one worker thread: no per-frame event-loop round trip, FFmpeg encodes in parallel.
        smoother=BarSmoother(fps); previous=smoother.value.copy()
        with pipe:
            for frame in range(seconds*fps):
                if halt.is_set(): return
                t=frame/fps
                bars=smoother.step(audio_bars(segment.waveform,t)).copy()
                pipe.write(frames.motion(segment.index,t,seconds,previous,bars,fps,came_from=segment.came_from).tobytes())
                previous=bars
    producer=asyncio.create_task(asyncio.to_thread(produce))
    try:
        async with asyncio.timeout(max(120,seconds*20)):
            await asyncio.shield(producer)
            await process.wait()
            await errors
        if process.returncode: raise MediaError('FFmpeg could not encode canvas')
    except (BrokenPipeError,ConnectionResetError) as exc:
        raise MediaError('FFmpeg stopped accepting frames') from exc
    finally:
        halt.set()
        await stop(process)
        await asyncio.gather(producer,return_exceptions=True)
        pipe.close()
        if not errors.done(): errors.cancel()
        await asyncio.gather(errors,return_exceptions=True)


async def render_movie(items,segments,directory,theme,ffmpeg,size=720,fps=60):
    if not segments: raise MediaError('No audio segments to render')
    directory.mkdir(parents=True,exist_ok=True)
    frames=await in_thread(CanvasFrames,items,theme,size)
    parts=[]
    for number,segment in enumerate(segments):
        path=directory/f'segment-{number:03d}.mp4'
        came_from=segments[number-1].index if number else -1
        await render_segment(frames,replace(segment,came_from=came_from),path,ffmpeg,fps)
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
