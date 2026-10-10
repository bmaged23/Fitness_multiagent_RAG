"""Add a readiness indicator to Streamlit's existing inline microphone."""
from pathlib import Path
import streamlit.components.v2 as components

microphone_status = components.component('inline_microphone_status',
    js=(Path(__file__).parent / 'assets/microphone_status.js').read_text())
