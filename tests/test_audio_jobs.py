

def test_ready_audio_player_is_below_reply():
    from io import BytesIO
    import numpy as np
    import soundfile as sf
    from streamlit.testing.v1 import AppTest
    output = BytesIO()
    sf.write(output, np.zeros(100), 24000, format='WAV')
    app = AppTest.from_string('''
import streamlit as st
from app.components.voice_ui import reply_audio
with st.chat_message('assistant'):
    st.markdown('Your reply')
    reply_audio(st.session_state['item'], 0)
''')
    app.session_state['item'] = {'content': 'Your reply', 'audio_by_voice': {'am_michael': output.getvalue()}}
    app.run(timeout=30)
    assert not app.exception
    assert len(app.get('audio')) == 1
    assert len(app.chat_message[0].get('audio')) == 1
    assert not any('sidebar' in caption.value for caption in app.caption)
