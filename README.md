# Voicewright
 An app using open source and free AI models that pipelines created AI voices and sound effects, and Turing text to speech using those crafted voices.

## Run it

Needs macOS with Python 3.11 or 3.12 (3.13 and newer won't work with the speech model).

1. `brew install python@3.11 ffmpeg`
2. `python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev,speech,voice-design]'`
3. `.venv/bin/voicewright`

The last step starts the app at <http://127.0.0.1:8765/> and opens it in your browser, then loads the speech model (Chatterbox) in the background. The first run downloads its weights from Hugging Face, about 4 GB; after that it loads in about 15 seconds and uses about 5 GB. `GET /jobs/current` shows the load while it runs, and a failed load is printed in the terminal. Without the `speech` or `voice-design` extra the app still runs, but anything that needs that model says how to install it. To start without loading any model, for working on the page, set `VOICEWRIGHT_NO_MODELS=1`. Running it again while it's up just opens the page, unless `--config` names a config file other than the default one. Use `--port` to pick another port.

### Convert a file

The Convert panel on the page turns an audio or video file (MP3, M4A, FLAC, OGG, AAC, WAV, or a video with sound) into the app's standard WAV, 16-bit mono, and lets you play or download it. The same conversion is `POST /convert` with the file as a form upload named `file`.

### Design a voice

The Voices area of the page does all of this: describe a voice and design it, then review each clip (play it, regenerate it, go back to an earlier take, or move the exaggeration and cfg sliders and hear the result), and accept it under a name or discard it. Draft voices left open show up there to resume. Saved Voices can be edited in place: hear new values, regenerate a preset, add a custom one, then accept or reject each new take. A bar at the top shows the running job and its step. A take you make plays as soon as it's ready, an open Voice card stays open while you work on it, and an error shows next to the button that caused it. The API behind it:

`POST /voices/design` with `{"description": "A gravelly older man, slow and calm."}` starts a job that designs a Draft voice. Qwen3-TTS designs the neutral clip, then one Emotion preset for each emotion in the Default emotion set (`GET /emotions/defaults`). The first run downloads its weights, about 8 GB. Follow the job at `GET /jobs/{id}`. Its result names the Draft voice: `GET /voices/drafts/{id}` lists its presets, and each preset's `clip_url` plays the clip. Draft voices are kept in the data folder's `drafts` folder and survive a restart.

To review a Draft voice, each of these starts a job and adds a take; no take is deleted while the draft is open:

- `POST /voices/drafts/{id}/presets/{emotion}/regenerate` designs a new take of one preset, or of the neutral clip.
- `POST /voices/drafts/{id}/presets/{emotion}/retune` with `{"exaggeration": 0.9, "cfg": 0.2}` speaks the preset's sample at those values, so you can hear them, and keeps them.
- `POST /voices/drafts/{id}/redesign` with `{"description": "…"}` changes the description and designs every preset again.

`PUT /voices/drafts/{id}/presets/{emotion}` with `{"take": "angry-1"}` goes back to an earlier take.

When the Draft voice sounds right, `POST /voices` with `{"draft_id": "…", "name": "Old Narrator"}` saves it to the library, in the data folder's `voices` folder, and removes the draft and its takes. A name already taken, ignoring case, gets 409. `DELETE /voices/drafts/{id}` discards a draft instead. `GET /voices/drafts` lists the drafts still open, for picking up after a restart. `GET /voices` lists saved Voices with their presets.

To edit a saved Voice, each of these starts a job that makes a pending take. The Voice changes only when you accept it (`POST /voices/{id}/takes/{take}/accept`); rejecting it (`DELETE /voices/{id}/takes/{take}`) leaves the preset as it was:

- `POST /voices/{id}/presets` with `{"name": "angry-soft"}` adds a custom preset. `sample`, `exaggeration`, and `cfg` are optional; the values start from neutral's.
- `POST /voices/{id}/presets/{emotion}/regenerate` designs a new clip for a preset. The neutral clip is locked, so this is refused for neutral.
- `POST /voices/{id}/presets/{emotion}/retune` with new values lets you hear them first.

`DELETE /voices/{id}/presets/{emotion}` removes any preset but neutral, and `DELETE /voices/{id}` deletes the Voice. The description can't be edited once the Voice is saved.

### Settings and data

On first run the app writes a config file to `~/.config/voicewright/config.toml` (or wherever `--config` points) and creates the app data folder it names, `~/Voicewright` by default, with `voices`, `drafts`, `sounds`, `cache`, and `saved` subfolders. To move the data folder, set `data_folder` to a full path or one starting with `~`. The config file also holds the Output cache size (5 to 10) and your Freesound API key, so it is created readable only by you. Keep it out of git.

## Develop

Before each commit, run the checks:

```sh
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
```

Tests run the app in-process against a fresh temporary data folder, so they never touch your real config or data. Every engine is faked and no test loads a real model.

The smoke tests load the real models. They render a short line and a 120-word passage, and design a whole Draft voice, then save the audio so you can listen. It's slow and runs only on Apple Silicon, so it's left out of the default run:

```sh
.venv/bin/pytest -m smoke -s
```
