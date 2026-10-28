import asyncio
import io
import os
from pathlib import Path
import tempfile
import unittest
import wave
import numpy as np
from PIL import Image
from bot.canvas.render import Segment, render_movie, CanvasFrames
from bot.canvas.process import run
from bot.lastfm import TrackInfo
from bot.themes import DEFAULT


def track(number, colour):
    out=io.BytesIO(); Image.new('RGB',(300,300),colour).save(out,format='PNG')
    return TrackInfo(number,f'Listener {number}',str(number),'Demo Artist',f'Song {number}',out.getvalue())


class RenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_sequential_audio_does_not_mix(self):
        ffmpeg=os.getenv('CANVAS_FFMPEG')
        if not ffmpeg: self.skipTest('Set CANVAS_FFMPEG for real encode integration test')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); segments=[]
            for i,freq in enumerate((440,880)):
                pcm=(np.sin(2*np.pi*freq*np.arange(32000)/16000)*.3).astype(np.float32)
                audio=root/f'{i}.wav'
                with wave.open(str(audio),'wb') as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                    wav.writeframes((pcm*32767).astype('<i2').tobytes())
                segments.append(Segment(i,audio,0,1,pcm[:16000]))
            result=await render_movie([track(1,'red'),track(2,'blue')],segments,root,DEFAULT,ffmpeg,size=320,fps=12)
            data=await run([ffmpeg,'-v','error','-i',result.path,'-vn','-ac','1','-ar','16000','-f','f32le','pipe:1'])
            pcm=np.frombuffer(data,dtype='<f4')
            self.assertAlmostEqual(len(pcm)/16000,2,delta=.12)
            for second,wanted,unwanted in ((.5,440,880),(1.5,880,440)):
                part=pcm[int((second-.15)*16000):int((second+.15)*16000)]
                spectrum=abs(np.fft.rfft(part*np.hanning(len(part))))
                bins=np.fft.rfftfreq(len(part),1/16000)
                a=spectrum[np.abs(bins-wanted).argmin()]; b=spectrum[np.abs(bins-unwanted).argmin()]
                self.assertGreater(a,20*b)
            self.assertTrue(result.path.stat().st_size>1000)

    def test_missing_track_still_has_a_card(self):
        frames=CanvasFrames([track(1,'red'),track(2,'blue'),track(3,'green')],DEFAULT,size=320)
        a=frames.frame(0,0,1,np.ones(16))
        b=frames.frame(2,0,1,np.ones(16))
        self.assertEqual(a.size,b.size)
        self.assertNotEqual(a.tobytes(),b.tobytes())
        self.assertEqual(frames.count,3)
