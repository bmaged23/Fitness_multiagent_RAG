# Streamlit demo recording

This video records the working Streamlit build from `/home/bmage/projects/Fitness_multiagent_RAG`, using a separate SQLite database and the fictional Sam Carter account. It does not use real trainee data.

## What is shown

- Login and a natural-language workout request.
- Retrieval-backed workout structure, followed by Week 1 exercise generation.
- Explicit user approval and saving of the workout program.
- Saved plan tables, week selection, a deload week, and PDF export.
- A microphone recording submitted through Streamlit's normal voice composer.
- Faster Whisper transcription, a real Coach response, and Kokoro reply playback.
- Returning to the saved plan and logging out.

## How the video was produced

Browser actions are automated with paced typing, clicks, scrolling, and a visible pointer. The microphone receives a synthetic spoken question; transcription and reply generation use the real application services. The reply soundtrack is the exact WAV generated and played by the app, combined with the captured video.

Generation waits are shortened and labeled with the observed elapsed time for this recording. Replies and saved plans are actual outputs. The workout and voice sections were recorded in separate browser sessions with the same fictional account.

The video does not exercise nutrition-plan generation or plan revisions. Timings are observations from one demo, not performance benchmarks.

## Fix found during rehearsal

Approving a generated workout previously sent the plan back through agent reconstruction, which could supply malformed data to validation and crash saving. Approval now validates and saves the stored Week 1 draft directly. The targeted draft-routing, nutrition-routing, and Streamlit suite passed **29 tests**; the recording also exercised a successful save and PDF download.

## Artifacts

- [Video](media/fitness-coach-demo.mp4)
- [Cover image](media/fitness-coach-demo-poster.png)
- [Chapters and edit metadata](media/fitness-coach-demo.json)

The video is H.264 with AAC audio at 1600 × 900 pixels. Recording tools, raw footage, credentials, and the demo database remain outside the published media directory.
