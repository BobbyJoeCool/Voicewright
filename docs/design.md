# Voicewright: Design Doc

*Local text-to-speech app with custom voices, inline emotion tags, and sound effects.*

Terms in this doc follow `GLOSSARY.md`.

## Goal

Create and save custom voices, then turn a tagged script into a finished audio file. A script can mix emotions, vocal effects in the speaker's voice, and regular sound effects:

```
[angry] I hate you! (scream) {explosion}
```

Everything runs locally and uses free, open-source models. The only network use is searching Freesound to add sounds to the local sound library; generation itself works offline.

## v1 scope

- One Voice per Script.
- Voices are created from a text description. Creating a Voice from an uploaded recording is a future feature, used in v1 only as a fallback if no voice-design model runs acceptably on the M2.
- Sound effects come from the local sound library and play in sequence, not over speech.
- Vocal effects are skipped with a warning until a model passes the vocal-effects test.
- The user works in a local web page served by the FastAPI backend.

## Environment

- MacBook with M2 chip, 24GB RAM
- Python 3.11 virtual environment (3.12 also works; 3.13 and newer do not, because `chatterbox-mlx` requires `>=3.11,<3.13`)
- ffmpeg (`brew install ffmpeg`)
- Only one large model in memory at a time. Chatterbox (hybrid-mlx) uses about 14 to 16GB.

## Models and services

| Role | Tool | Status |
|---|---|---|
| Speech and voice cloning | Chatterbox via `chatterbox-mlx` (`hybrid-mlx` backend), MIT license | Tested, works |
| Voice design from a text description | VoxCPM2 (Apache 2.0) or Qwen3-TTS VoiceDesign | Untested on Mac |
| Vocal effects in the speaker's voice | Candidate: Chatterbox Turbo (`chatterbox-tts`; inline `[laugh]`, `[chuckle]`, `[sigh]`, `[cough]`). Breeze TTS 2 ruled out: documented for Linux with NVIDIA CUDA only, and its weights are non-commercial | Untested on Mac |
| Sound effects | Local sound library, filled by searching Freesound in the app | Not started |
| Audio conversion and assembly | ffmpeg through `pydub` | Not started |
| Backend and UI | FastAPI, serving a local web page | Not started |

## Pipeline overview

1. Design a voice from a description
2. Review the draft voice and its emotion presets
3. Save the voice to the library
4. Parse the script into segments
5. Validate the script against the voice and the sound library
6. Map emotion tags to emotion presets
7. Generate each segment
8. Assemble the output
9. Present it from the output cache, and save only on request

## 1. Audio converter

Every audio file that enters the app goes through the converter before anything else uses it. In v1 that means sounds downloaded from Freesound (and imported recordings, if the import fallback is used).

- Uses ffmpeg through `pydub`. Handles MP3, M4A, FLAC, OGG, AAC, and audio from video files.
- Converts everything to one standard format: 16-bit PCM WAV, mono.
- Also available as a standalone feature for converting files without creating a voice.

## 2. Voice creation

1. **Describe the voice**, for example "gravelly older man, slow and calm."
2. **Generate the neutral reference clip** reading a neutral sample sentence.
3. **Generate the emotion presets:** the same voice reading sample sentences for each emotion in the default emotion set.
4. **Review:** the user listens to each clip and can accept it, regenerate it, edit the description, or adjust its `exaggeration` and `cfg` values.
5. **Accept or discard:** accepting saves the clips and preset values to the voice library. Discarding deletes the draft.

### Default emotion set

Every new Voice starts with the same list of emotions (v1: neutral, angry, sad, excited, plus any others chosen during implementation). The list lives in a data file so it can grow without backend changes.

### Draft voices

A Voice under review is a draft voice. Its clips live in a draft area, separate from the output cache, so regenerating samples never evicts other samples still under review. Draft voices survive an app restart or crash: on startup the app offers to resume or discard each one.

### Editing a saved Voice

- Emotion presets can be added, retuned, regenerated, or removed after the Voice is saved. New or regenerated presets go through the same review step.
- The neutral reference clip is locked. Every emotion preset is cloned from it, so replacing it would change who the Voice sounds like. A new identity means a new Voice.

### Voice consistency

Designing each emotion separately from the text description may produce a slightly different person each time. To prevent this:

- Design **only the neutral voice** from the description.
- Create emotion presets by **cloning from the neutral clip**, adding the emotion through style instructions (VoxCPM2 supports this, e.g. `(slightly faster, cheerful tone)`) or through Chatterbox's `exaggeration` and `cfg` settings.
- Qwen3-TTS's "Voice Design then Clone" workflow is built for this approach. Its clone model takes no emotion instruction, so with Qwen the emotion presets come from Chatterbox's settings.

## 3. Voice library

Each saved Voice contains:

- A neutral reference clip (about 15 seconds of clean speech)
- One emotion preset per emotion: a reference clip plus its tuning values

Example preset file:

```json
{
  "angry":   { "clip": "voices/narrator_angry.wav",   "exaggeration": 0.7,  "cfg": 0.3 },
  "sad":     { "clip": "voices/narrator_sad.wav",     "exaggeration": 0.3,  "cfg": 0.5 },
  "excited": { "clip": "voices/narrator_excited.wav", "exaggeration": 0.65, "cfg": 0.35 },
  "neutral": { "clip": "voices/narrator_neutral.wav", "exaggeration": 0.5,  "cfg": 0.5 }
}
```

These numbers are starting points to tune by ear. Presets live in JSON so adding an emotion never requires backend changes. The tuning values are Chatterbox settings; switching speech models would mean retuning every Voice.

## 4. Script parsing and validation

The script is split into an ordered list of segments. Each segment type uses a different bracket style so the parser can tell them apart:

| Syntax | Meaning | Scope |
|---|---|---|
| `[angry]` | Emotion tag | Applies until the next emotion tag |
| `(laugh)` | Vocal effect in the speaker's voice | Single effect |
| `{explosion}` | Sound effect | Single effect |

Example: `[angry] I hate you! (scream) {explosion}` becomes:

1. Speech, angry: "I hate you!"
2. Vocal effect: scream
3. Sound effect: explosion

Untagged text uses the neutral preset.

Before any generation starts, the script is validated:

- Every emotion tag must match an emotion preset on the chosen Voice.
- Every sound effect name must match an entry in the sound library.
- If anything is missing, the script is rejected with a list of every missing emotion and sound. Each missing sound links to the Freesound picker.
- Vocal effects that no model can produce yet are reported as warnings and skipped; they don't reject the script.

## 5. Emotion mapping

Each emotion tag looks up that Voice's emotion preset: its reference clip, `exaggeration`, and `cfg`. To get a different delivery for one line, add a new emotion preset (for example `angry-soft`). Per-line overrides are a future feature.

Tuning guidance from the `chatterbox-mlx` README:

- Dramatic delivery: lower `cfg` (about 0.3) and higher `exaggeration` (about 0.7)
- Higher `exaggeration` speeds up speech; lower `cfg` compensates
- Reference audio should match the target language to avoid accent transfer

## 6. Segment generation

- **Speech:** Chatterbox with the preset's clip and settings. Use `generate_long` for text over about 50 words. Load the model once at startup, not per request.
- **Vocal effects:** the weakest part of the pipeline. Chatterbox only speaks text, so phonetic spellings of laughs or screams sound stilted. Chatterbox Turbo is the first candidate to test. Its tags use square brackets, so the app translates the script's `(laugh)` into Turbo's `[laugh]`; Turbo has no `exaggeration` or `cfg`, so it would be used only for vocal-effect segments. Until one passes, vocal effects are skipped with a warning.
- **Sound effects:** read from the local sound library. Generation never calls the network.

### Sound library

- Each entry has a name (the text inside `{}`), an audio file, its source, and its license.
- To add a sound, the user searches Freesound in the app, previews results, and picks one. The app downloads it, converts it, and stores it with its license and attribution.
- One audio file per name in v1.

## 7. Assembly

- Stitch segments in order with `pydub`
- Add short gaps or crossfades between segments
- Normalize volume across segments
- Export one WAV (MP3 optional)

Sound effects play in sequence with speech in v1.

## 8. Output storage

Generated audio is presented but not kept by default.

1. Every output goes into a **temporary output cache**. Draft voice clips do not; they live in the draft area (section 2).
2. The cache keeps the last N outputs (setting: 5 to 10). When it's full, the oldest is deleted.
3. A **Save** action copies an output into a separate **saved folder** that cleanup never touches, with a sidecar record of the script text, the Voice, the preset values used, and credits and licenses for every sound effect used.
4. The output cache is cleared on app startup. The draft area is not.

## Backend endpoints (draft)

| Endpoint | Purpose |
|---|---|
| `POST /convert` | Convert an uploaded file to standard WAV |
| `POST /voices/design` | Generate a draft voice and its emotion presets from a description |
| `GET /voices/drafts` | List draft voices (used for resume-on-startup) |
| `DELETE /voices/drafts/{id}` | Discard a draft voice |
| `POST /voices` | Save an accepted draft voice to the library |
| `GET /voices` | List saved voices |
| `PATCH /voices/{id}` | Add, retune, regenerate, or remove emotion presets |
| `GET /sounds` | List the sound library |
| `GET /sounds/search` | Search Freesound |
| `POST /sounds` | Download a Freesound result into the sound library |
| `POST /generate` | Validate a tagged script against a voice, then return the output |
| `POST /outputs/{id}/save` | Copy a cached output and its sidecar to the saved folder |

## Open questions and tests

1. **Vocal effects:** can any model produce convincing laughs, screams, and sighs in a cloned voice? (Highest risk. Doesn't block v1.) Test: `spikes/test_turbo_effects.py`.
2. **Voice consistency:** design one voice, create angry and sad variants both by separate design and by cloning from neutral, and compare. Test: `spikes/test_voxcpm_design.py` and `spikes/test_chatterbox_clone.py`.
3. **Mac support:** do VoxCPM2 and Qwen3-TTS run acceptably on the M2? If neither does, v1 falls back to creating Voices from an uploaded recording. Test: `spikes/test_voxcpm_design.py` and `spikes/test_qwen_design.py`.
4. **Memory:** confirm the load-and-unload pattern keeps memory pressure out of the red when switching between models.

## Future versions

Deferred from v1, planned for later:

- **Multiple Characters per Script:** define Characters and assign each one a Voice, so one script can be a multi-voice scene. Needs a speaker syntax.
- **Create a Voice from an uploaded recording** through the audio converter (unless v1 already needed it as the fallback).
- **Sound effects over speech:** overlay or "embedded" sound effects such as ambience under dialogue, alongside the v1 sequential behavior.
- **Generated sound effects:** create new sounds with Stable Audio Open (loaded only when needed, unloaded afterward) and save them to the sound library.
- **More default emotions** in the default emotion set.
- **Save custom emotions to the default set,** so an emotion added to one Voice can be offered to every new Voice.
- **Per-line overrides** of `exaggeration` and `cfg` within a script.
- **Re-render** a saved output from its sidecar record.

## Content policy

Voices are designed or recorded with consent. The app is not used to clone real people's voices without their permission.
