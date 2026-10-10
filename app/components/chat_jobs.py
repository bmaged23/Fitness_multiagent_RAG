"""Session-owned chat jobs that survive Streamlit page reruns."""
from concurrent.futures import Future
from threading import Thread
import logging


def start_chat_job(build_agent, turn, agent, messages, trainee_id, text):
    future = Future()
    # The worker owns a copy; session state is updated only by the UI thread.
    history = list(messages)
    def work():
        try:
            current_agent = agent if agent is not None else build_agent()
            response = turn(current_agent, history, trainee_id, text)
            future.set_result((current_agent, history, response))
        except Exception:
            logging.exception('Background coaching turn failed')
            future.set_result((agent, history,
                'I couldn’t finish that request. Your saved plans are still available. Please try again.'))
    Thread(target=work, name=f'coach-{trainee_id}', daemon=True).start()
    return future


def finish_chat_job(state):
    job = state.get('chat_job')
    if job is None or not job.done():
        return False
    agent, messages, response = job.result()
    if agent is not None:
        state['agent'] = agent
    state['messages'] = messages
    state['chat'].append({'role': 'assistant', 'content': response})
    del state['chat_job']
    return True
