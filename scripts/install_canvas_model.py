"""Fetch the versioned Google YAMNet Lite model; validate before atomic install."""
import hashlib
import os
from pathlib import Path
import urllib.request

URL='https://storage.googleapis.com/mediapipe-models/audio_classifier/yamnet/float32/1/yamnet.tflite'
SHA256='4d8b4a53282dc83ef04e3e7dbc4fbc98082e34e44ed798e16c3a0cdd4c584faf'


def main():
    path=Path(os.getenv('CANVAS_MODEL_PATH','.cache/canvas_models/yamnet.tflite'))
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==SHA256:
        print('YAMNet already installed and verified'); return
    with urllib.request.urlopen(URL,timeout=60) as response:
        data=response.read(8*1024*1024)
    if hashlib.sha256(data).hexdigest()!=SHA256: raise RuntimeError('YAMNet checksum mismatch')
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)
    print(f'Installed verified YAMNet ({len(data)} bytes) at {path}')


if __name__=='__main__': main()
