"""Download optional English voice models; run once before using voice controls."""
from huggingface_hub import snapshot_download

if __name__ == '__main__':
    snapshot_download('Systran/faster-whisper-base.en', allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary*'])
    snapshot_download('hexgrad/Kokoro-82M', allow_patterns=['config.json', 'kokoro-v1_0.pth', 'voices/am_michael.pt', 'voices/af_heart.pt'])
    print('Speech models downloaded.')
