from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from streamlit.testing.v1 import AppTest
from app.components import chat_ui
from fitness_multiagent_rag.db import connection

ROOT = Path(__file__).parents[1]


@pytest.fixture
def database(monkeypatch, tmp_path):
    path = tmp_path / 'ui.db'
    monkeypatch.setattr(connection, 'SQLITE_DB_PATH', path)
    with connection.get_db() as conn:
        conn.executescript((ROOT / 'db/schema.sql').read_text())
    return path


def test_signup_login_and_password_never_in_context(database):
    password = 'Example123!'
    trainee = chat_ui.signup('test_user', password, 'Test User', 'test@example.com', '123456',
                              25, 'male', 'Bodybuilding', 'Beginner', ['Dumbbell Only'])
    assert chat_ui.login('test_user', 'wrong') is None
    assert chat_ui.login('test_user', password).id == trainee.id
    assert password not in str(chat_ui.initial_messages(trainee))
    with connection.get_db_ro() as conn:
        hashed = conn.execute('SELECT password_hash FROM trainee_auth').fetchone()[0]
        assert hashed != password


def test_login_gate_hides_chat_and_does_not_build_agent(monkeypatch):
    from fitness_multiagent_rag.agents.coach import agent
    monkeypatch.setattr(agent, 'build_coach_agent', lambda: pytest.fail('Agent built before login'))
    app = AppTest.from_file(str(ROOT / 'app/streamlit_app.py')).run(timeout=30)
    assert not app.exception
    assert len(app.chat_input) == 0
    assert [tab.label for tab in app.tabs] == ['Log in', 'Sign up']
    assert any(widget.proto.type == 1 for widget in app.text_input)


def test_authenticated_ui_displays_chat(database, monkeypatch):
    trainee = chat_ui.signup('test_user', 'Example123!', 'Test User', 'test@example.com', '123456',
                              25, 'male', 'Bodybuilding', 'Beginner', ['Dumbbell Only'])
    from fitness_multiagent_rag.agents.coach import agent
    monkeypatch.setattr(agent, 'build_coach_agent', lambda: object())
    monkeypatch.setattr(chat_ui, '_nutrition_response', lambda *args: 'Stored meals with portions')
    app = AppTest.from_file(str(ROOT / 'app/streamlit_app.py'))
    app.session_state['trainee_id'] = trainee.id
    app.session_state['username'] = 'test_user'
    app.session_state['chat'] = []
    app.session_state['messages'] = chat_ui.initial_messages(trainee)
    app.run(timeout=30)
    assert not app.exception
    assert len(app.chat_input) == 1
    assert app.radio[0].options == ['Chat', 'My plans']
    app.chat_input[0].set_value('show me nutrition details').run(timeout=30)
    assert not app.exception
    if 'chat_job' in app.session_state:
        app.session_state['chat_job'].result(timeout=10)
        app.run(timeout=30)
    assert app.session_state['chat'][-1]['content'] == 'Stored meals with portions'
    assert any('Stored meals with portions' in message.value for message in app.markdown)
    app.radio[0].set_value('My plans').run(timeout=30)
    assert not app.exception
    assert len(app.chat_input) == 0
    assert any(title.value == 'My plans' for title in app.title)
    app.radio[0].set_value('Chat').run(timeout=30)
    assert not app.exception
    assert app.session_state['chat'][-1]['content'] == 'Stored meals with portions'
    assert len(app.chat_input) == 1
    logout = next(button for button in app.button if button.label == 'Log out')
    logout.click().run(timeout=30)
    assert not app.exception
    assert len(app.chat_input) == 0
    assert 'trainee_id' not in app.session_state


def test_chat_adapter_preserves_tool_history_and_context(monkeypatch):
    messages = [HumanMessage(content='profile context')]
    monkeypatch.setattr(chat_ui, '_nutrition_response', lambda *args: None)
    monkeypatch.setattr(chat_ui, '_draft_response', lambda *args: None)
    monkeypatch.setattr(chat_ui.crud, 'get_active_plan', lambda _: None)
    monkeypatch.setattr(chat_ui, 'classify_intent', lambda *args, **kwargs: 'general_chat')
    captured = []
    def stream(agent, candidate, **kwargs):
        captured.extend(candidate)
        assert kwargs['show_trace'] is False
        return 'Hello', [AIMessage(content='Hello')], {}
    monkeypatch.setattr(chat_ui, '_stream_turn', stream)
    assert chat_ui.chat_turn(object(), messages, 1, 'hello') == 'Hello'
    assert len(messages) == 3
    assert captured[0].content == 'profile context'
    assert messages[-1].content == 'Hello'
