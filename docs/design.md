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
- Voices are created from a text description with Qwen3-TTS VoiceDesign. Creating a Voice from an uploaded recording is a future feature (the v1 fallback was not needed: Qwen passed the M2 spike).
- Sound effects come from the local sound library and play in sequence, not over speech.
- Vocal effects are parsed but skipped with a warning. No model passed the vocal-effects test well enough (see Open questions and tests), so rendering them is a future feature.
- The user works in a local web page served by the FastAPI backend.

## Environment

- MacBook with M2 chip, 24GB RAM
- Python 3.11 virtual environment (3.12 also works; 3.13 and newer do not, because `chatterbox-mlx` requires `>=3.11,<3.13`)
- ffmpeg (`brew install ffmpeg`)
- Only one large model in memory at a time. Chatterbox (hybrid-mlx) uses about 14 to 16GB; Qwen3-TTS VoiceDesign peaked at 5.8GB in the spike.

## Models and services

| Role | Tool | Status |
|---|---|---|
| Speech and voice cloning | Chatterbox via `chatterbox-mlx` (`hybrid-mlx` backend: the `ChatterboxTTSMLX` class, loaded with `device="mps"`), MIT license | Tested, works |
| Voice design from a text description, neutral clip and every emotion preset | Qwen3-TTS VoiceDesign via `mlx-audio` (`mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16`). VoxCPM2 also ran but sounded weaker and needs about 13GB | Chosen in step 0.2 |
| Vocal effects in the speaker's voice | None in v1. Chatterbox Turbo (`chatterbox-tts`) runs on the M2 but only its chuckle was convincing (see Open questions and tests). Breeze TTS 2 ruled out: documented for Linux with NVIDIA CUDA only, and its weights are non-commercial | Deferred |
| Sound effects | Local sound library, filled by searching Freesound in the app (high-quality previews; originals need OAuth2) | Built in phase 3 |
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
2. **Generate the neutral reference clip:** Qwen3-TTS designs it from the description, reading a neutral sample sentence.
3. **Generate the emotion presets:** Qwen3-TTS designs each one from the description plus the emotion (for example "... Speaking in a sad tone."), reading that emotion's sample sentence.
4. **Review:** the user listens to each clip and can accept it, regenerate it, edit the description, or adjust its `exaggeration` and `cfg` values.
5. **Accept or discard:** accepting saves the clips and preset values to the voice library. Discarding deletes the draft.

### Default emotion set

Every new Voice starts with the same list of emotions (v1: neutral, angry, sad, excited, plus any others chosen during implementation). The list lives in a data file so it can grow without backend changes.

### Draft voices

A Voice under review is a draft voice. Its clips live in a draft area, separate from the output cache, so regenerating samples never evicts other samples still under review. Draft voices survive an app restart or crash: on startup the app offers to resume or discard each one.

### Editing a saved Voice

- Emotion presets can be added, retuned, regenerated, or removed after the Voice is saved. New or regenerated presets go through the same review step.
- The neutral reference clip and the description are locked. The neutral clip is the take the user accepted as the Voice, and every preset, including ones added later, is designed from the description, so changing either would change who the Voice sounds like. A new identity means a new Voice.

### Voice consistency

The original plan was to design only the neutral clip and clone every emotion from it, so each emotion would be the same person. The step 0.2 spikes changed that (ADR `docs/adr/0003-qwen-designs-every-emotion-preset.md`): cloning kept the voice only close, and Qwen3-TTS designing each emotion from the description sounded better. Each emotion preset is therefore designed separately from the description.

Designing each emotion separately can still produce a slightly different person. The safeguard is the review step: the user regenerates one preset until it matches the neutral clip. If drift turns out to be a real problem, the tested fallback is cloning each emotion from the neutral clip with VoxCPM2's style instructions.

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

Parsing rules (step 4.1):

- Names inside markers are matched ignoring case: `[Angry]` is `[angry]`, `{Door-Slam}` is `{door-slam}`.
- An Emotion tag or Vocal effect is one word: lowercase letters, digits, `-` and `_`, starting with a letter. A Sound effect follows the sound-name rule in section 6.
- A marker closes on its own line, before any other bracket. Otherwise it's a parse error at the opening bracket. So are a closing bracket with no opener, an empty marker, and a marker holding something that can't be a name (`(and then)`). Each error gives its character position and its line and column, and parsing carries on so every error is reported at once.
- Whitespace inside speech is collapsed to single spaces; speech that is only whitespace is dropped.
- A Script with nothing to say or play (empty, or only Vocal effects and tags) is rejected with a parse error.
- An Emotion tag is checked against the Voice even if no speech follows it.

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
- **Vocal effects:** skipped with a warning in v1. Chatterbox only speaks text, so phonetic spellings sound stilted, and Chatterbox Turbo's tags (`[laugh]` etc., translated from the script's `(laugh)`) passed only for chuckle in the spike. See Future versions.
- **Sound effects:** read from the local sound library. Generation never calls the network.

### Sound library

- Each entry has a name (the text inside `{}`), an audio file, its source, and its license.
- To add a sound, the user searches Freesound in the app, previews results, and picks one. The app downloads it, converts it, and stores it with its license and attribution.
- What the app downloads is Freesound's high-quality preview (OGG, about 192 kbps), not the original upload. An API key covers search, sound details, and previews; original files need OAuth2, a per-user login flow with a registered app and a redirect, which is a lot of machinery for a local app. A 192 kbps preview is plenty for sound effects in a mono WAV Output. Downloading originals through OAuth2 is a future feature.
- One audio file per name in v1.
- Names are lowercase letters, digits, `-` and `_`, starting with a letter or digit, up to 60 characters (`{door-slam}`). A name typed with capitals is the same sound.
- Adding under a name already taken is refused; replacing is a separate action that keeps the name.
- The API key comes from the `FREESOUND_API_KEY` environment variable, or else `freesound_api_key` in the config file, read on each search so a new key works without a restart.

## 7. Assembly

- Stitch segments in order with `pydub`
- Add short gaps or crossfades between segments
- Normalize volume across segments
- Export one WAV (MP3 optional)

Sound effects play in sequence with speech in v1.

Starting values (step 4.2, to tune by ear): 350 ms of silence between pieces, a 10 ms fade at each end of every piece against clicks, every piece brought to -20 dBFS RMS without its peak passing -1 dBFS, and everything resampled to the highest sample rate among the pieces (Chatterbox speaks at 24 kHz, Freesound previews are often 44.1 kHz).

What a Script uses (each emotion's Reference clip and values, each sound and its credit) is copied when generation starts, so editing the Voice or the Sound library during the job doesn't change that Output.

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
| `PUT /sounds/{name}` | Replace the sound behind a name with another Freesound result |
| `DELETE /sounds/{name}` | Remove a sound |
| `GET /sounds/{name}/audio` | Play a sound |
| `POST /scripts/check` | Check a Script against a Voice: 200 with `warnings`, or 422 listing `missing_emotions`, `missing_sounds`, and `parse_errors` |
| `POST /scripts/generate` | Check the Script (422, no job, if rejected), then start a job that renders it into one Output; progress counts Segments |
| `GET /outputs` | List the Output cache, newest first, each with its record |
| `GET /outputs/{id}`, `GET /outputs/{id}/audio` | One Output, and its audio |
| `POST /outputs/{id}/save` | Copy a cached output and its sidecar to the saved folder |

## Open questions and tests

Step 0.2 ran these spikes on the M2 on 2026-10-30. The scripts are in `spikes/`. RTF is seconds of work per second of audio.

1. **Mac support and voice design: Qwen3-TTS chosen.**
   - Qwen3-TTS VoiceDesign: neutral clip matched the description and was clean, RTF 1.37, peak RSS 5.8GB, memory pressure green. Judged "a lot better" than VoxCPM2, with much better emotions.
   - VoxCPM2: ran, neutral clip matched the description, peak RSS 13.8GB, memory pressure yellow. Emotions only partly landed (sad sounded thoughtful, excited sounded upset).
   - The recording-upload fallback is not needed.
2. **Voice consistency: each emotion designed by Qwen3-TTS** (ADR 0003).
   - VoxCPM2 style-cloning from VoxCPM2's neutral clip: the same man, emotions partly.
   - Chatterbox cloning from either engine's neutral clip (starting exaggeration/cfg values): close to the same man, emotions came through, RTF 2.5 to 2.9, green.
   - VoxCPM2 style-cloning from Qwen's neutral clip: close to the same man, emotions came through, better than VoxCPM2 alone, RTF 2.5 to 3.9, peak RSS 13.3GB.
   - The user judged that cloning was what made the voice drift and chose to design each emotion with Qwen. Not checked: whether Qwen's separately designed emotions sound like the same man. Review in the Draft voice is the safeguard.
3. **Vocal effects: not in v1.** Chatterbox Turbo ran on `mps`, RTF about 2.0, green, and stayed in the cloned voice. `[chuckle]` was convincing; `[laugh]` and `[cough]` sounded forced or fake; `[sigh]` came out as breathing in; `(scream)`, which Turbo doesn't document, was read aloud as the word. The user chose to leave vocal effects out of v1.
4. **Memory:** each model ran alone without going red. Only VoxCPM2 reached yellow, and v1 doesn't use it. Step 2.2 confirmed the load-and-unload switch between Qwen and Chatterbox on the M2. Chatterbox loaded holds 2.0 GB of MLX and 1.0 GB of MPS memory, and both drop to zero when it closes. Qwen loaded holds 4.3 GB, and reaches a 7.3 GB MLX peak while designing a clip. Chatterbox comes back afterwards. The process footprint peaked at 14 GB while designing a full Draft voice: four clips in 47 seconds, with a 15-second neutral clip. The full smoke test is still step 5.2.

Library notes from the spikes, for the real engines:

- `chatterbox-mlx` (1.0.6 in the spike, 1.3.1 in the app): the hybrid backend is the `ChatterboxTTSMLX` class; `from_pretrained(device="mps")`. `device="hybrid-mlx"` is rejected. Its `generate_long` splits text over 50 words into chunks of about 35 words.
- Resemble's `perth` watermarker (used by Chatterbox) imports `pkg_resources`, which setuptools 82 removes. `chatterbox-mlx` 1.3.1 itself requires `setuptools<82`; on 81 the watermarker loads, with a deprecation warning.
- Measured in step 1.4 on the M2 (1.3.1): the speech model loads in about 12 seconds and the app's footprint is about 5 GB, well under the 14 to 16 GB planned for. A 120-word passage comes out at 22 to 29 seconds (about 4.4 words a second, in both 1.0.6 and 1.3.1). With a robotic Reference clip (macOS `say`), a chunk sometimes ends early; to check with a designed clip once voice design exists (step 2.2).

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
- **Vocal effects** in the speaker's voice. Chatterbox Turbo's `[chuckle]` already works; laugh, cough, sigh, and scream need a better model or approach.

## Content policy

Voices are designed or recorded with consent. The app is not used to clone real people's voices without their permission.
