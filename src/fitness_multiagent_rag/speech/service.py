from functools import lru_cache
from io import BytesIO
from threading import Lock
import re

STT_REPO = 'Systran/faster-whisper-base.en'
TTS_REPO = 'hexgrad/Kokoro-82M'
VOICE = 'am_michael'
VOICES = {'am_michael': 'Man — Michael', 'af_heart': 'Woman — Heart'}
_lock = Lock()


def _require_gpu():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('Voice features require CUDA GPU access. Text chat is still available.')


@lru_cache(maxsize=1)
def _stt_model():
    _require_gpu()
    from huggingface_hub import snapshot_download
    from faster_whisper import WhisperModel
    path = snapshot_download(STT_REPO, local_files_only=True,
        allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary*'])
    return WhisperModel(path, device='cuda', compute_type='int8_float16', local_files_only=True)


@lru_cache(maxsize=1)
def _tts_pipeline():
    _require_gpu()
    import torch
    from huggingface_hub import hf_hub_download
    from kokoro import KModel, KPipeline
    config = hf_hub_download(TTS_REPO, 'config.json', local_files_only=True)
    weights = hf_hub_download(TTS_REPO, 'kokoro-v1_0.pth', local_files_only=True)
    model = KModel(repo_id=TTS_REPO, config=config, model=weights).to('cuda').eval()
    pipeline = KPipeline(lang_code='a', repo_id=TTS_REPO, model=model, device='cuda')
    return pipeline


@lru_cache(maxsize=2)
def _voice_tensor(voice):
    import torch
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(TTS_REPO, f'voices/{voice}.pt', local_files_only=True)
    return torch.load(path, map_location='cpu', weights_only=True)


def transcribe(audio_bytes: bytes) -> str:
    import soundfile as sf
    if not audio_bytes or len(audio_bytes) > 10 * 1024 * 1024:
        raise ValueError('Record a voice note shorter than two minutes.')
    info = sf.info(BytesIO(audio_bytes))
    if info.duration > 120:
        raise ValueError('Record a voice note shorter than two minutes.')
    with _lock:
        segments, _ = _stt_model().transcribe(BytesIO(audio_bytes), language='en',
            beam_size=1, vad_filter=True, condition_on_previous_text=False)
        text = ' '.join(segment.text.strip() for segment in segments).strip()
    if not text:
        raise ValueError('No speech detected. Please record again.')
    return text


def spoken_text(text: str) -> str:
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'(?m)^\s*[#>•*-]+\s*', '', text)
    text = text.replace('**', '').replace('`', '').replace('\u202f', ' ')
    text = re.sub(r'(\d+)\s*[×x]\s*(\d+)', r'\1 sets of \2', text)
    return text.strip()


def synthesize(text: str, voice: str = VOICE) -> bytes:
    import numpy as np
    import soundfile as sf
    if voice not in VOICES:
        raise ValueError('Choose a supported voice.')
    text = spoken_text(text)
    if not text:
        raise ValueError('There is no text to read aloud.')
    if len(text) > 15000:
        raise ValueError('This reply is too long to read at once. Ask Alex for a shorter section.')
    with _lock:
        pipeline = _tts_pipeline()
        voice_tensor = _voice_tensor(voice)
        chunks = [result.audio.detach().cpu().numpy() for result in pipeline(text, voice=voice_tensor, speed=1)
                  if result.audio is not None]
    if not chunks:
        raise RuntimeError('Speech generation returned no audio.')
    output = BytesIO()
    sf.write(output, np.concatenate(chunks), 24000, format='WAV', subtype='PCM_16')
    return output.getvalue()
