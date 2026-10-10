"""Run with: python -m streamlit run app/streamlit_app.py"""
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

import streamlit as st
from app.components.chat_ui import login, signup, initial_messages, chat_turn
from app.components.chat_jobs import start_chat_job, finish_chat_job
from app.components.audio_jobs import finish_audio_jobs, pending_audio_jobs
from app.components.voice_ui import message_input, reply_audio, audio_player
from app.components.plan_views import format_chat_reply, render_my_plans
from app.components.plan_pdf import nutrition_pdf, workout_pdf
from config.settings import SQLITE_DB_PATH
from fitness_multiagent_rag.agents.coach.identity import COACH_NAME
from fitness_multiagent_rag.agents.coach.agent import build_coach_agent, _VALID_GOALS, _VALID_EQUIPMENT
from fitness_multiagent_rag.agents.coach.memory import memory_backend
from fitness_multiagent_rag.db import crud, nutrition
from fitness_multiagent_rag.agents.designer.drafts import read_draft

st.set_page_config(page_title=f'{COACH_NAME} · Fitness Coach', page_icon='💬', layout='centered')

if not SQLITE_DB_PATH.exists():
    from scripts.init_db import init_db
    init_db()


def authenticate(trainee):
    st.session_state['trainee_id'] = trainee.id
    st.session_state['username'] = trainee.username
    st.session_state['chat'] = []
    st.session_state['messages'] = initial_messages(trainee)
    st.session_state.pop('agent', None)
    st.rerun()


if 'trainee_id' not in st.session_state:
    st.title(f'Welcome to {COACH_NAME}')
    st.write('Your workouts, nutrition, and coaching in one conversation.')
    login_tab, signup_tab = st.tabs(['Log in', 'Sign up'])
    with login_tab:
        with st.form('login', clear_on_submit=True):
            username = st.text_input('Username', key='login_username')
            password = st.text_input('Password', type='password', key='login_password')
            submitted = st.form_submit_button('Log in', type='primary', width='stretch')
        if submitted:
            trainee = login(username, password)
            if trainee is None:
                st.error('Incorrect username or password.')
            else:
                authenticate(trainee)
    with signup_tab:
        with st.form('signup', clear_on_submit=True):
            name = st.text_input('Full name')
            username = st.text_input('Choose a username')
            password = st.text_input('Choose a password', type='password')
            confirmation = st.text_input('Confirm password', type='password')
            st.caption('Use at least 8 characters, including a letter, number, and symbol.')
            email = st.text_input('Email')
            phone = st.text_input('Phone')
            age = st.number_input('Age', min_value=1, max_value=120, value=25)
            gender = st.selectbox('Gender', ['male', 'female'])
            goal = st.selectbox('Training goal', sorted(_VALID_GOALS))
            level = st.selectbox('Experience', ['Beginner', 'Novice', 'Intermediate', 'Advanced'])
            equipment = st.multiselect('Available equipment', sorted(_VALID_EQUIPMENT), default=['Dumbbell Only'])
            submitted = st.form_submit_button('Create account', type='primary', width='stretch')
        if submitted:
            try:
                if password != confirmation:
                    raise ValueError('Passwords do not match.')
                if not equipment:
                    raise ValueError('Select your available equipment.')
                authenticate(signup(username, password, name, email, phone, age, gender, goal, level, equipment))
            except (ValueError, sqlite3.IntegrityError) as exc:
                st.error(str(exc))
    st.stop()

trainee = crud.get_trainee_by_id(st.session_state['trainee_id'])
if trainee is None:
    st.session_state.clear()
    st.rerun()
trainee.username = st.session_state.get('username')
finish_chat_job(st.session_state)
finish_audio_jobs(st.session_state)


@st.fragment(run_every='1s')
def pending_chat_status():
    job = st.session_state.get('chat_job')
    audio_jobs = pending_audio_jobs(st.session_state)
    if (job is not None and job.done()) or any(audio.done() for audio in audio_jobs):
        st.rerun()
    if job is not None:
        st.info('Alex is working in the background. You can browse My plans while you wait.')
    audio_player()



with st.sidebar:
    st.title(COACH_NAME)
    page = st.radio('Navigate', ['Chat', 'My plans'], key='page', label_visibility='collapsed')
    st.caption('Your fitness & nutrition coach')
    st.selectbox('Reply voice', ['am_michael', 'af_heart'], key='tts_voice',
                 format_func=lambda voice: {'am_michael': 'Man — Michael', 'af_heart': 'Woman — Heart'}[voice])
    st.write(f'**{trainee.name}**')
    st.caption(f'{trainee.goal or "Goal not set"} · {trainee.fitness_level or "Experience not set"}')
    st.divider()
    pending_chat_status()
    st.subheader('Your plans')
    workout = crud.get_active_plan(trainee.id)
    draft = read_draft(trainee.id)
    if workout:
        st.write(f'Workout · Active · {workout.duration_weeks} weeks')
    elif draft:
        st.write('Workout · Draft awaiting approval')
    else:
        st.caption('No workout program yet')
    meal_plan = nutrition.get_plan(trainee.id)
    meal_draft = nutrition.get_plan(trainee.id, 'draft')
    st.write('Nutrition · Active' if meal_plan else 'Nutrition · Draft' if meal_draft else 'No nutrition plan yet')
    st.download_button('Download nutrition plan',
        nutrition_pdf(meal_plan['plan_json'], trainee.name) if meal_plan else b'',
        'nutrition_plan.pdf', 'application/pdf', disabled=meal_plan is None, width='stretch')
    st.download_button('Download workout program',
        workout_pdf(workout.plan_json, trainee.name) if workout else b'',
        'workout_program.pdf', 'application/pdf', disabled=workout is None, width='stretch')
    st.divider()
    if st.button('Log out', width='stretch'):
        try:
            memory_backend.end_session(trainee.id)
        except Exception:
            logging.exception('Could not finalize coaching session')
        st.session_state.clear()
        st.rerun()

if page == 'My plans':
    st.title('My plans')
    render_my_plans(trainee.id, draft)

else:
    st.title(f'Chat with {COACH_NAME}')
    st.caption('Build a program, review your meals, or ask a training question.')
    if not st.session_state['chat']:
        with st.chat_message('assistant'):
            st.markdown(f'Hi {trainee.name.split()[0]}! What would you like to work on today?')
    for index, item in enumerate(st.session_state['chat']):
        with st.chat_message(item['role']):
            st.markdown(format_chat_reply(item['content']) if item['role'] == 'assistant' else item['content'])
            if item['role'] == 'assistant':
                reply_audio(item, index)

    busy = 'chat_job' in st.session_state
    text = message_input(disabled=busy)
    if text and not busy:
        st.session_state['chat'].append({'role': 'user', 'content': text})
        st.session_state['chat_job'] = start_chat_job(
            build_coach_agent, chat_turn, st.session_state.get('agent'),
            st.session_state['messages'], trainee.id, text)
        st.rerun()
