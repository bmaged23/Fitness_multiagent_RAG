"""Background speech jobs independent of the selected Streamlit page."""
from concurrent.futures import Future
from threading import Thread


def start_audio_job(synthesize, text, voice):
    future = Future()
    def work():
        try:
            future.set_result(synthesize(text, voice=voice))
        except Exception as exc:
            future.set_exception(exc)
    Thread(target=work, name='reply-audio', daemon=True).start()
    return future


def finish_audio_jobs(state):
    changed = False
    for item in state.get('chat', []):
        jobs = item.get('audio_jobs', {})
        for voice, job in list(jobs.items()):
            if not job.done():
                continue
            try:
                item.setdefault('audio_by_voice', {})[voice] = job.result()
                item.setdefault('audio_errors', {}).pop(voice, None)
            except Exception as exc:
                item.setdefault('audio_errors', {})[voice] = str(exc)
            del jobs[voice]
            changed = True
    return changed


def pending_audio_jobs(state):
    return [job for item in state.get('chat', []) for job in item.get('audio_jobs', {}).values()]
