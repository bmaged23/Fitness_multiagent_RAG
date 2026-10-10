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
    submission = st.chat_input('Message Alex…', accept_audio=True, audio_sample_rate=16000, disabled=disabled)
    if submission is None:
        return None
    try:
        with st.spinner('Preparing your message…'):
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
        st.session_state['audio_selection'] = (index, voice)
        if voice not in audio_by_voice and voice not in jobs:
            from fitness_multiagent_rag.speech.service import synthesize
            item.setdefault('audio_errors', {}).pop(voice, None)
            jobs[voice] = start_audio_job(synthesize, item['content'], voice)
        st.rerun()
    if voice in jobs:
        st.caption('Generating audio in the background…')
    elif voice in audio_by_voice:
        st.caption('Audio ready — use the player in the sidebar.')
    if item.get('audio_errors', {}).get(voice):
        st.error(f"Could not generate audio: {item['audio_errors'][voice]}")


def audio_player():
    """Keep the selected reply player mounted on both Chat and My plans."""
    selection = st.session_state.get('audio_selection')
    if selection is None:
        return
    index, voice = selection
    chat = st.session_state.get('chat', [])
    if index >= len(chat):
        return
    item = chat[index]
    audio = item.get('audio_by_voice', {}).get(voice)
    if audio:
        st.caption('Reply audio · ' + ('Michael' if voice == 'am_michael' else 'Heart'))
        st.audio(audio, format='audio/wav', autoplay=False)
    elif voice in item.get('audio_jobs', {}):
        st.caption('Generating reply audio in the background…')
    elif voice in item.get('audio_errors', {}):
        st.error(f"Could not generate audio: {item['audio_errors'][voice]}")
