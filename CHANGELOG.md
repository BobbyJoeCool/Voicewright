# Changelog

All notable changes to Voicewright are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-11-13

The first release: a local web app that designs custom voices, keeps a library of
sound effects, and turns tagged Scripts into finished audio, all on a Mac.

### Added

- **App and setup.** One command (`voicewright`) starts the app on
  <http://127.0.0.1:8765/> and opens it. A config file and app data folder are created
  on first run; the Output cache size and Freesound API key live in the config. Running
  it again while it's up just opens the page.
- **App window.** The page opens in its own Chrome, Edge, Brave, or Chromium app window
  (no tabs or address bar), falling back to the usual browser when none is installed,
  with `--tab`, or when `BROWSER` is set. It can be installed as a web app with a Dock
  icon.
- **Styled page.** A sidebar switches between Voices, Sounds, Scripts, and Convert, with
  a job bar showing the running job and its step. Dark and light themes, a narrow-window
  layout, and styled confirmation dialogs in place of browser pop-ups.
- **Audio converter.** Turn an audio or video file into the app's standard WAV (16-bit
  mono) from the Convert area, by drag and drop, or through `POST /convert`.
- **Job runner.** Long work (model loads, voice design, generation) runs one job at a
  time and reports progress at `GET /jobs/current` and `GET /jobs/{id}`.
- **Speech engine.** Chatterbox loads in the background at startup and speaks every
  line.
- **Voice design.** Describe a voice and Qwen3-TTS designs a Draft voice with a neutral
  clip and one preset for each emotion in the Default emotion set.
- **Voice review.** Play, regenerate, or retune each preset (exaggeration and cfg), go
  back to any earlier take, or redesign the whole draft. Drafts survive a restart.
- **Voice library.** Accept a Draft voice under a unique name, or discard it. Edit a
  saved Voice through pending takes: add a custom preset, regenerate or retune one, then
  accept or reject each take. Remove presets or delete the Voice.
- **Sound library.** Search Freesound, preview a result, check its license, and add it
  under a name as standard WAV with its credit. Replace or remove sounds. Searching works
  without a restart when a key is added, and the rest of the app keeps working offline.
- **Scripts.** Write a Script with `[emotion]` and `{sound}` tags. Check reports every
  problem at once (missing emotions, missing sounds, malformed tags) with buttons to fix
  them. The editor highlights tags, offers a tag palette, and generates with ⌘/Ctrl+Enter.
- **Outputs.** Generate a Script into one WAV with short gaps and even volume. The last
  5 to 10 Outputs are kept until restart. Save one for good with a JSON record of its
  Script, Voice, preset values, and every sound's credit and license. Download Outputs
  and Saved outputs from the page.

- **Smoke test.** `tests/smoke/test_full_smoke.py` runs the whole flow on the real models
  with every outside connection refused, and fails if macOS memory pressure reaches
  critical.
- **QA record.** [`docs/qa-v1.md`](docs/qa-v1.md) shows how each of the spec's 61 user
  stories was checked against the running app.
- **README demo.** The README opens with a screenshot and a real, unedited sample Output.

### Not in this release

- Vocal effects such as `(laugh)` are recognized in a Script but skipped with a warning.

[1.0.0]: https://github.com/BobbyJoeCool/Voicewright/releases/tag/v1.0.0
