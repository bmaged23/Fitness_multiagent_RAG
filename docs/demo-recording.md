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

Browser actions are automated with paced typing, clicks, scrolling, and a visible pointer. The microphone receives a synthetic spoken question; transcription and reply generation use the real application services. The voice section uses the exact WAV generated and played by the app, combined with the captured video. Synthetic Kokoro narration explains the planning and download sections. Original microphone and reply audio are retained and amplified.

Generation waits are shortened and labeled with the observed elapsed time for this recording. Replies and saved plans are actual outputs. The workout and voice sections were recorded in separate browser sessions with the same fictional account.

The revised video also shows nutrition-plan generation and approval, followed by both PDF downloads, opening the actual downloaded documents, and scrolling every page to the bottom. The downloaded workout PDF was parsed successfully (13 pages); the nutrition PDF was parsed successfully (2 pages). Plan revisions are not exercised. Timings are observations from one demo, not performance benchmarks.

## Fix found during rehearsal

Approving a generated workout previously sent the plan back through agent reconstruction, which could supply malformed data to validation and crash saving. Approval now validates and saves the stored Week 1 draft directly. The targeted draft-routing, nutrition-routing, and Streamlit suite passed **29 tests**; the recording also exercised a successful save and PDF download.

## Artifacts

- [Video download](https://raw.githubusercontent.com/bmaged23/Fitness_multiagent_RAG/master/docs/media/fitness-coach-demo.mp4)
- [Browser player](demo.html)
- [Cover image](media/fitness-coach-demo-poster.png)
- [Chapters and edit metadata](media/fitness-coach-demo.json)

The video is H.264 with AAC audio at 1600 × 900 pixels. Recording tools, raw footage, credentials, and the demo database remain outside the published media directory.

## Document viewing verification

The final recording downloads both files again through the app, then opens their actual pages in a local viewer using PyMuPDF rendering. All 13 workout pages and both nutrition pages are scrolled through to the bottom. The PDF content is rendered from the downloaded bytes, without reconstructing the document from extracted text. The viewer is recording tooling, not a new application feature.

The standalone player includes explicit Play with sound and Fullscreen buttons. Browser verification measures the live decoded audio signal connected to the browser output and checks fullscreen entry and exit. Recording narration is synthetic; STT input and the app's TTS reply remain the real recorded samples.

## Narration timing revision

The soundtrack was rebuilt from complete WAV recordings instead of trimming an already mixed soundtrack. All narration segments are checked against explicit visual timing windows, and no two speech segments overlap. The complete microphone sample and actual app-generated reply audio are retained. The visual stream is byte-identical to the approved document walkthrough. Expanded narration explains agent delegation, Qdrant versus SQLite, plan approval, and the downloaded document contents. The media JSON records the final speech timeline.
