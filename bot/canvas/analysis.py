"""Sparse vocal inference and repetition analysis; never a loudness-only chorus guess."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import zipfile
import numpy as np

from .process import MediaError, in_thread, run

MODEL_SHA256='4d8b4a53282dc83ef04e3e7dbc4fbc98082e34e44ed798e16c3a0cdd4c584faf'
SR=16000


@dataclass
class Features:
    energy: np.ndarray
    vocals: np.ndarray
    repetition: np.ndarray
    onset: np.ndarray
    duration: float


def choose_excerpt(features: Features, seconds: int) -> float:
    f=features
    if f.duration < seconds or not len(f.energy) or float(np.max(f.energy)) < 1e-5:
        raise ValueError('Audio is silent or too short')
    energy=np.asarray(f.energy,float)
    relative=np.clip(energy/max(np.percentile(energy,85),1e-8),0,1)
    quiet=energy < max(1e-5,np.percentile(energy,85)*.08)
    vocal=bool(np.count_nonzero(f.vocals>.15) >= max(3,len(energy)*.08))
    scores=[]
    for start in range(int(f.duration-seconds)+1):
        sl=slice(start,start+seconds)
        if quiet[sl].mean()>.15: continue
        score=.3*relative[sl].mean()+.35*f.repetition[sl].mean()-2*quiet[sl].mean()
        if vocal:
            score+=1.5*np.clip(f.vocals[sl]/.5,0,1).mean()
            score-=.35*float(f.vocals[start]<.1)
        # Mild intro/outro penalty, never exclude a chorus that starts immediately.
        score-=.12*float(start<8 or start+seconds>f.duration-5)
        score+=.04*float(f.onset[start])
        scores.append((score,start))
    if not scores: raise ValueError('No non-silent excerpt')
    return float(max(scores,key=lambda row:row[0])[1])


class Analyser:
    def __init__(self, model_path: Path):
        self.model_path=model_path
        self.interpreter=None

    def _load(self):
        if self.interpreter is not None: return
        if not self.model_path.exists(): raise MediaError('Run scripts/install_canvas_model.py first')
        if hashlib.sha256(self.model_path.read_bytes()).hexdigest()!=MODEL_SHA256:
            raise MediaError('Unexpected YAMNet model checksum')
        from ai_edge_litert.interpreter import Interpreter
        self.interpreter=Interpreter(model_path=str(self.model_path),num_threads=1)
        self.interpreter.allocate_tensors()
        self.input=self.interpreter.get_input_details()[0]
        self.output=self.interpreter.get_output_details()[0]
        with zipfile.ZipFile(self.model_path) as archive:
            labels=archive.read('yamnet_label_list.txt').decode().splitlines()
        self.voice_ids=[i for i,name in enumerate(labels) if name in {'Singing','Choir','Rapping','Chant','Child singing','Synthetic singing'}]

    def features(self, pcm: Path):
        self._load()
        samples=np.memmap(pcm,dtype='<f4',mode='r')
        try:
            duration=len(samples)/SR
            n=int(duration)
            if n<1: raise ValueError('Empty audio')
            energy=np.empty(n); voices=np.empty(n); fingerprints=[]
            window=np.hanning(SR)
            frequencies=np.fft.rfftfreq(SR,1/SR)
            valid=(frequencies>=80)&(frequencies<=5000)
            pitches=np.rint(69+12*np.log2(frequencies[valid]/440)).astype(int)%12
            for second in range(n):
                part=np.array(samples[second*SR:(second+1)*SR],dtype=np.float32)
                energy[second]=np.sqrt(np.mean(part*part))
                self.interpreter.set_tensor(self.input['index'],part[:15600])
                self.interpreter.invoke()
                scores=self.interpreter.get_tensor(self.output['index'])[0]
                voices[second]=max(scores[self.voice_ids])
                power=np.abs(np.fft.rfft(part*window))[valid]
                chroma=np.bincount(pitches,weights=power,minlength=12)
                # Normalised chroma describes harmonic repetition across song sections.
                fingerprints.append(chroma/(np.linalg.norm(chroma)+1e-8))
            vectors=np.asarray(fingerprints,dtype=np.float32)
            similarity=vectors@vectors.T
            # Require four consecutive similar seconds, separated by at least 16 seconds.
            sequence=similarity.copy()
            for shift in (1,2,3):
                sequence[:-shift,:-shift]+=similarity[shift:,shift:]
            sequence/=4
            rows=np.arange(n)
            sequence[np.abs(rows[:,None]-rows[None,:])<16]=0
            repetition=np.clip((sequence.max(axis=1)-.8)/.2,0,1) if n>32 else np.zeros(n)
            onset=np.maximum(0,np.diff(energy,prepend=energy[0]))
            onset/=max(float(onset.max()),1e-8)
            return Features(energy,voices,repetition,onset,duration)
        finally:
            samples._mmap.close()


async def analyse_audio(audio: Path, directory: Path, analyser: Analyser, ffmpeg: str, seconds: int):
    pcm=directory/'analysis.f32'
    await run([ffmpeg,'-v','error','-nostdin','-y','-i',audio,'-t','600','-vn','-ac','1','-ar',str(SR),'-f','f32le',pcm],timeout=45)
    features=await in_thread(analyser.features,pcm)
    start=choose_excerpt(features,seconds)
    # Snap at most half a second to a nearby rising energy edge; keep exact clip length.
    samples=np.memmap(pcm,dtype='<f4',mode='r')
    try:
        lo=max(0,start-.5); hi=min(features.duration-seconds,start+.5)
        choices=np.arange(lo,hi+.001,.05)
        def rise(t):
            a=int(t*SR); b=min(len(samples),a+800)
            before=samples[max(0,a-800):a]
            return float(np.mean(samples[a:b]**2)-(np.mean(before**2) if len(before) else 0))
        if len(choices): start=float(max(choices,key=rise))
        excerpt=np.array(samples[int(start*SR):int((start+seconds)*SR)],dtype=np.float32)
    finally:
        samples._mmap.close()
    pcm.unlink(missing_ok=True)
    return start,excerpt
