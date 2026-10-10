"""UI-independent authentication and chat adapters shared by Streamlit tests."""
from langchain_core.messages import AIMessage, HumanMessage
from fitness_multiagent_rag.agents.coach.auth import _verify_password, _hash_password, validate_password, validate_username_format
from fitness_multiagent_rag.agents.coach.main import _build_context_block, _stream_turn, _nutrition_response, _draft_response
from fitness_multiagent_rag.agents.coach.routing import classify_intent
from fitness_multiagent_rag.agents.coach.memory import memory_backend
from fitness_multiagent_rag.db import crud
from fitness_multiagent_rag.db.models import Trainee


def login(username: str, password: str):
    username = username.strip().lower()
    auth = crud.get_auth_by_username(username)
    if not auth or not _verify_password(password, auth.password_hash):
        return None
    return crud.get_trainee_by_username(username)


def signup(username: str, password: str, name: str, email: str, phone: str,
           age: int, gender: str, goal: str, level: str, equipment: list[str]):
    username = username.strip().lower()
    for valid, reason in [validate_username_format(username), validate_password(password)]:
        if not valid:
            raise ValueError(reason)
    if not name.strip() or '@' not in email or not phone.strip():
        raise ValueError('Enter your name, email, and phone number.')
    if crud.username_exists(username):
        raise ValueError('That username is already taken.')
    return crud.create_trainee_with_auth(Trainee(name=name.strip(), email=email.strip(), phone=phone.strip(),
        age=age, gender=gender, goal=goal, fitness_level=level, equipment_available=equipment),
        username, _hash_password(password))


def initial_messages(trainee):
    return [HumanMessage(content=_build_context_block(trainee, memory_backend.load(trainee.id)))]


def chat_turn(agent, messages: list, trainee_id: int, text: str, on_reply=None) -> str:
    previous = next((str(m.content) for m in reversed(messages) if isinstance(m, AIMessage)), '')
    response = _nutrition_response(trainee_id, text, previous)
    if response is None:
        response = _draft_response(trainee_id, text, previous)
    if response is not None:
        messages.extend([HumanMessage(content=text), AIMessage(content=response)])
        if on_reply:
            on_reply(response)
        return response
    intent = classify_intent(text, crud.get_active_plan(trainee_id) is not None, previous_reply=previous)
    candidate = messages + [HumanMessage(content=f'[intent: {intent}]\n{text}')]
    response, new_messages, _ = _stream_turn(agent, candidate, show_trace=False, on_reply=on_reply)
    if not response:
        response = 'I couldn’t complete that response. Please try again.'
    messages.extend(candidate[len(messages):] + new_messages)
    if not new_messages or not isinstance(new_messages[-1], AIMessage):
        messages.append(AIMessage(content=response))
    return response
