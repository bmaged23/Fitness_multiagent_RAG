from threading import Event
from app.components.chat_jobs import start_chat_job, finish_chat_job


def test_navigation_during_request_preserves_result_and_history():
    started, release = Event(), Event()
    agent = object()
    def turn(current, history, trainee_id, text):
        assert current is agent and trainee_id == 2
        started.set()
        assert release.wait(5)
        history.extend([text, 'Finished answer'])
        return 'Finished answer'
    state = {'messages': ['Profile'], 'chat': [{'role': 'user', 'content': 'Question'}]}
    job = start_chat_job(lambda: agent, turn, None, state['messages'], 2, 'Question')
    state['chat_job'] = job
    try:
        assert started.wait(5)
        state['page'] = 'My plans'
        assert not finish_chat_job(state)
        assert state['messages'] == ['Profile']
        assert not job.done()
    finally:
        release.set()
    job.result(timeout=5)
    assert finish_chat_job(state)
    assert state['page'] == 'My plans'
    assert state['messages'] == ['Profile', 'Question', 'Finished answer']
    assert state['chat'][-1]['content'] == 'Finished answer'
    assert not finish_chat_job(state)
    assert len(state['chat']) == 2


def test_job_failure_completes_and_allows_next_message():
    def fail(*args):
        raise RuntimeError('Backend failed')
    state = {'messages': [], 'chat': []}
    state['chat_job'] = start_chat_job(lambda: object(), fail, None, [], 2, 'hello')
    state['chat_job'].result(timeout=5)
    assert finish_chat_job(state)
    assert 'chat_job' not in state
    assert 'couldn’t finish' in state['chat'][0]['content']
