"""Optional voice input in the chat composer and audio playback for replies."""
import logging
import streamlit as st


def submitted_text(submission) -> str | None:
    """Convert a submitted chat recording to the same query used for typed input."""
    if submission is None:
        return None
    if isinstance(submission, str):
        return submission.strip() or None
    text = (submission.text or '').strip()
    if submission.audio is not None:
        from fitness_multiagent_rag.speech.service import transcribe
        transcript = transcribe(submission.audio.getvalue())
        text = '\n'.join(part for part in (text, transcript) if part)
    return text or None


def message_input(*, disabled=False) -> str | None:
    submission = st.chat_input('Message Alex…', accept_audio=True,
                               audio_sample_rate=16000, disabled=disabled)
    from app.components.microphone_status import microphone_status
    microphone_status(key='inline_microphone_readiness', height=0)
    if submission is None or disabled:
        return None
    try:
        with st.spinner('Transcribing your voice message…' if getattr(submission, 'audio', None)
                        else 'Preparing your message…'):
            return submitted_text(submission)
    except Exception as exc:
        logging.exception('Voice transcription failed')
        st.error(f'Could not transcribe: {exc}')
        return None


def reply_audio(item: dict, index: int):
    from app.components.audio_jobs import start_audio_job
    voice = st.session_state.get('tts_voice', 'am_michael')
    audio_by_voice = item.setdefault('audio_by_voice', {})
    jobs = item.setdefault('audio_jobs', {})
    if st.button('Listen to this reply', key=f'listen_{index}', disabled=voice in jobs):
        if voice not in audio_by_voice and voice not in jobs:
            from fitness_multiagent_rag.speech.service import synthesize
            item.setdefault('audio_errors', {}).pop(voice, None)
            jobs[voice] = start_audio_job(synthesize, item['content'], voice)
        st.rerun()
    if voice in jobs:
        st.caption('Generating audio in the background…')
    elif voice in audio_by_voice:
        st.audio(audio_by_voice[voice], format='audio/wav', autoplay=False)
    if item.get('audio_errors', {}).get(voice):
        st.error(f"Could not generate audio: {item['audio_errors'][voice]}")
