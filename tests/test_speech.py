from io import BytesIO
from types import SimpleNamespace
import pytest
import soundfile as sf
import numpy as np
from fitness_multiagent_rag.speech import service


def test_transcription_consumes_segments_and_keeps_english(monkeypatch):
    out = BytesIO()
    sf.write(out, np.zeros(16000), 16000, format='WAV')
    calls = []
    def run(audio, **kwargs):
        calls.append(kwargs)
        return iter([SimpleNamespace(text=' Show me '), SimpleNamespace(text=' my nutrition plan. ')]), None
    monkeypatch.setattr(service, '_stt_model', lambda: SimpleNamespace(transcribe=run))
    assert service.transcribe(out.getvalue()) == 'Show me my nutrition plan.'
    assert calls[0]['language'] == 'en'


def test_long_recording_rejected_before_model_load(monkeypatch):
    monkeypatch.setattr(service, '_stt_model', lambda: pytest.fail('Model must remain unloaded'))
    out = BytesIO()
    sf.write(out, np.zeros(16000 * 121), 16000, format='WAV')
    with pytest.raises(ValueError, match='two minutes'):
        service.transcribe(out.getvalue())


def test_empty_speech_is_not_sent(monkeypatch):
    out = BytesIO()
    sf.write(out, np.zeros(16000), 16000, format='WAV')
    monkeypatch.setattr(service, '_stt_model', lambda: SimpleNamespace(transcribe=lambda *a, **k: (iter([]), None)))
    with pytest.raises(ValueError, match='No speech'):
        service.transcribe(out.getvalue())


def test_text_for_audio_removes_markdown():
    assert service.spoken_text('## Workout\n- **Squats:** 3×10\n```json\n{}\n```') == 'Workout\nSquats: 3 sets of 10'


def test_chat_recording_becomes_agent_query(monkeypatch):
    from app.components.voice_ui import submitted_text
    calls = []
    def transcribe(audio):
        calls.append(audio)
        return 'Show me my nutrition plan.'
    monkeypatch.setattr(service, 'transcribe', transcribe)
    submitted = SimpleNamespace(text='', audio=BytesIO(b'recorded audio'))
    assert submitted_text(submitted) == 'Show me my nutrition plan.'
    assert calls == [b'recorded audio']
    assert submitted_text(' hello ') == 'hello'
    assert submitted_text(None) is None


def test_transcription_failure_does_not_send_partial_query(monkeypatch):
    from app.components.voice_ui import submitted_text
    def fail(_):
        raise ValueError('No speech detected')
    monkeypatch.setattr(service, 'transcribe', fail)
    with pytest.raises(ValueError, match='No speech'):
        submitted_text(SimpleNamespace(text='partial', audio=BytesIO(b'audio')))
