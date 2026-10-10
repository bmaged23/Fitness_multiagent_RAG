# Publishing the demo video

The repository contains a 4:54 narrated MP4 with the actual microphone sample, app-generated reply speech, nutrition approval, and both PDF downloads followed by opening and scrolling all document pages. It is approximately 9.3 MiB and uses browser-compatible H.264/AAC with fast-start metadata.

## README links

The README thumbnail links directly to the raw MP4, avoiding GitHub's repository file-preview page and its “can't show files that are this big” error. Depending on the browser, the raw link plays the video or downloads it. Push the revised media file before expecting the remote link to show the new recording.

## Inline playback on GitHub

For an inline player, edit the README using GitHub's browser editor and drag `docs/media/fitness-coach-demo.mp4` into the editor. GitHub uploads it as an attachment and inserts a `github.com/user-attachments/assets/...` URL. Keep that generated attachment URL in the README and preview before committing. No attachment URL has been generated automatically for this project.

GitHub's [official file attachment documentation](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files) lists MP4 support and a 10 MB video limit for free plans; this recording fits that limit.

## Standalone browser player

`docs/demo.html` provides standard browser playback and sound controls. Serve the repository's `docs` directory locally:

```bash
python -m http.server 8000 --directory docs
```

Open `http://localhost:8000/demo.html`, click Play, and enable sound. The page can also be hosted with GitHub Pages, but Pages has not been enabled by this change. GitHub's repository view displays HTML source rather than running the player.
