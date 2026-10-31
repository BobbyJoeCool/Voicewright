## Problem Statement

I want to make finished audio clips, such as narration, character lines, and short scenes, in custom voices I design myself, with emotion, non-verbal sounds, and sound effects, entirely on my own Mac and with free, open-source models. Today that means juggling separate TTS tools, cloning scripts, sound sites, and an audio editor, re-typing settings every time, and getting a slightly different "person" each time I ask for a new emotion. There is no single place to design a voice once, keep it, and then turn a tagged script into a finished file.

## Solution

Voicewright v1 is a local web app (a page served by a local FastAPI backend) with three areas:

- **Voices:** describe a voice in words. The app designs a neutral Reference clip, then clones the Default emotion set from it so every Emotion preset sounds like the same person. I review each clip, regenerate or retune it, and accept the Draft voice into my library. Later I can add, retune, regenerate, or remove Emotion presets; the neutral clip stays locked.
- **Sounds:** a local Sound library. I search Freesound from inside the app, preview results, and pick one; the app downloads and converts it and keeps its license and attribution.
- **Scripts:** I pick one Voice, paste a Script such as `[angry] I hate you! (scream) {explosion}`, and generate. The app checks the whole Script first and rejects it, listing every missing emotion and sound, before spending minutes on generation. It then renders each Segment, assembles one WAV Output, and plays it. Outputs are temporary unless I save them; a Saved output keeps a record of the Script, Voice, preset values, and sound credits.

Vocal effects such as `(laugh)` are skipped with a warning until a model passes the vocal-effects spike. Everything except the Freesound search runs offline. Terms follow `GLOSSARY.md`; the design is in `docs/design.md`.

## User Stories

### Creating a Voice

1. As a creator, I want to describe a voice in plain words (e.g. "gravelly older man, slow and calm"), so that I can get a voice without having a recording of anyone.
2. As a creator, I want the app to generate a neutral Reference clip of about 15 seconds from my description, so that the Voice has one clear identity to clone from.
3. As a creator, I want the app to generate one Emotion preset for each emotion in the Default emotion set, cloned from the neutral clip, so that every emotion sounds like the same person.
4. As a creator, I want to play each clip of a Draft voice in the page, so that I can judge it by ear before keeping it.
5. As a creator, I want to regenerate a single Emotion preset without regenerating the others, so that one bad take doesn't cost me the good ones.
6. As a creator, I want to regenerate the neutral clip while the Voice is still a Draft voice, so that I can try again until the identity is right.
7. As a creator, I want to edit the description of a Draft voice and regenerate, so that I can steer the voice toward what I imagined.
8. As a creator, I want to adjust an Emotion preset's exaggeration and cfg values and hear the result, so that I can tune its delivery.
9. As a creator, I want to accept a Draft voice under a name I choose, so that it joins my library and becomes usable in Scripts.
10. As a creator, I want to discard a Draft voice, so that abandoned experiments don't clutter my disk.
11. As a creator, I want every clip I generate while reviewing a Draft voice to stay available until I accept or discard it, so that later regenerations never delete takes I haven't decided on.
12. As a creator, I want my Draft voices to survive an app restart or crash, so that I don't lose a half-finished Voice when the Mac runs out of memory.
13. As a creator, I want the app to offer to resume or discard each surviving Draft voice when it starts, so that I can pick up where I left off.
14. As a creator, I want to be told clearly if I try to accept a Voice name that already exists, so that I don't overwrite a Voice by accident.
15. As a creator, I want the page to show that a voice is being generated and roughly which step it's on, so that I know the app hasn't frozen during a long model run.

### Managing saved Voices

16. As a creator, I want to see a list of my saved Voices, so that I can pick one for a Script.
17. As a creator, I want to see which Emotion presets a Voice has, so that I know which Emotion tags I can use with it.
18. As a creator, I want to play any saved Emotion preset, so that I can remember how a Voice sounds.
19. As a creator, I want to add a new Emotion preset (e.g. `angry-soft`) to a saved Voice by giving it a name, an optional sample sentence, and starting values, so that a Script that needs it can be rendered.
20. As a creator, I want a new or regenerated Emotion preset on a saved Voice to go through the same listen-and-accept review, so that a bad take never silently replaces a good one.
21. As a creator, I want to retune an existing Emotion preset's values, so that I can fix a delivery without recreating the Voice.
22. As a creator, I want to remove any Emotion preset except neutral from a saved Voice, so that I can drop emotions I never use without breaking untagged text.
23. As a creator, I want the neutral Reference clip of a saved Voice to be locked, so that editing never turns the Voice into a different person.
24. As a creator, I want to delete a saved Voice, so that I can clear out Voices I no longer want.
25. As a creator, I want new Voices to start with the Default emotion set (at least neutral, angry, sad, excited), so that common scripts work without extra setup.

### Sound library

26. As a creator, I want to search Freesound from inside the app, so that I don't have to download and convert sounds by hand.
27. As a creator, I want to preview Freesound results before picking one, so that I choose the right sound.
28. As a creator, I want to see each result's license before picking it, so that I avoid sounds I can't use the way I intend.
29. As a creator, I want to save a picked sound under a name I choose, so that `{that-name}` in a Script plays it.
30. As a creator, I want picked sounds converted to the app's standard WAV format automatically, so that any source format works in assembly.
31. As a creator, I want each Sound library entry to keep its source, author, and license, so that I can credit it later.
32. As a creator, I want to list and play the sounds in my Sound library, so that I know what names are available.
33. As a creator, I want to replace the sound behind a name, so that I can swap a weak explosion for a better one without editing Scripts.
34. As a creator, I want to remove a sound from the library, so that I can clean up sounds I don't use.
35. As a creator, I want a clear message when Freesound can't be reached or my API key is missing, so that I know why search isn't working while everything else still does.

### Writing and generating a Script

36. As a creator, I want to pick one saved Voice for a Script, so that the whole Script is spoken in that Voice.
37. As a creator, I want to write `[emotion]` to change emotion until the next Emotion tag, so that I can direct delivery inline.
38. As a creator, I want untagged text to use the neutral preset, so that simple Scripts need no tags.
39. As a creator, I want to write `{name}` to place a Sound effect between speech, so that my Output includes it in order.
40. As a creator, I want to write `(name)` to place a Vocal effect, so that my Scripts are ready for when vocal effects are supported.
41. As a creator, I want the app to check the whole Script before generating and list every Emotion tag the Voice lacks, so that I can fix them all at once instead of waiting minutes for a failed run.
42. As a creator, I want the same check to list every Sound effect name missing from the Sound library, each with a way to search Freesound for it, so that I can fill the gaps quickly.
43. As a creator, I want unsupported Vocal effects reported as warnings and skipped, rather than rejecting the Script, so that the rest of my Output still renders.
44. As a creator, I want malformed tags (e.g. an unclosed `[angry`) reported with their position, so that I can find and fix them.
45. As a creator, I want long passages of speech to render without cutting off, so that narration works as well as short lines.
46. As a creator, I want the Output assembled as one WAV with short gaps between Segments and even volume, so that it sounds finished rather than stitched.
47. As a creator, I want to play the Output in the page as soon as it's ready, so that I can judge it immediately.
48. As a creator, I want the page to show generation progress (e.g. Segment 3 of 7), so that I know how long to wait.
49. As a creator, I want to be told if a generation is already running when I start another, so that I don't overload memory with two runs.

### Outputs

50. As a creator, I want my last several Outputs (a setting from 5 to 10) kept temporarily, so that I can compare recent takes without saving each one.
51. As a creator, I want the oldest temporary Output removed automatically when the limit is reached, so that disk use stays bounded.
52. As a creator, I want to save an Output, so that it's kept permanently and never cleaned up.
53. As a creator, I want a Saved output to come with a record of the Script text, Voice, preset values, and credits and licenses for every Sound effect used, so that I can reproduce it or credit sounds when I share it.
54. As a creator, I want temporary Outputs cleared when the app starts, so that old scratch work doesn't accumulate.
55. As a creator, I want to download an Output or Saved output from the page, so that I can use the file elsewhere.

### Audio converter

56. As a creator, I want to convert an audio or video file (MP3, M4A, FLAC, OGG, AAC, video audio) to the app's standard WAV, so that I can prepare audio even outside voice creation.

### Running the app

57. As a creator, I want to start the app with one command and open it in my browser at a local address, so that it feels like an app, not a pile of scripts.
58. As a creator, I want the app to keep only one large model in memory at a time, so that my 24GB Mac doesn't go into the red.
59. As a creator, I want generation to work with no internet connection, so that the app is truly local.
60. As a creator, I want the app to tell me plainly when a model fails to load or runs out of memory, so that I know what happened and the app doesn't hang.
61. As a portfolio owner, I want the repo's README to show what the app does near the top, so that potential employers see a working demo.

## Implementation Decisions

### Modules

- **Audio converter:** turns any supported audio or video file into the standard format (16-bit PCM WAV, mono) using ffmpeg through pydub. Used by the Sound library and the standalone convert endpoint. Interface: convert(input file) → standard WAV, or a clear unsupported-format error.
- **Script parser:** turns Script text into an ordered list of Segments (speech with its current emotion, Vocal effect, Sound effect). Emotion tags are state that carries forward; untagged speech is neutral; whitespace-only speech between markers is dropped. Malformed or unclosed brackets are parse errors with character positions.
- **Script checker:** given parsed Segments, a Voice, the Sound library, and the vocal-effect engine's capability, returns either "ready" plus warnings, or a rejection listing every missing emotion and every missing sound name. Nothing is generated on rejection.
- **Voice library:** owns saved Voices and Draft voices. A Voice holds its name, its description, its locked neutral Reference clip, and its Emotion presets (Reference clip, exaggeration, cfg). Stored as files on disk: one folder per Voice with WAVs plus a JSON preset file in the shape shown in `docs/design.md` section 3 (`clip`, `exaggeration`, `cfg`). Draft voices live in a separate draft area that is not cleared on startup. Adding, regenerating, or retuning a preset on a saved Voice produces a take held in the draft area (so it survives restart) that replaces the preset only when accepted. The neutral preset cannot be removed, and the neutral Reference clip cannot be replaced, once the Voice is saved.
- **Default emotion set:** a data file listing the emotions every new Voice starts with and the sample sentence and starting exaggeration/cfg for each. v1 ships at least neutral, angry, sad, excited. A custom Emotion preset added to a saved Voice takes its name from the user, uses the user's sample sentence or a generic one, and starts from the neutral preset's values unless the user sets others.
- **Sound library:** owns named sounds: one standard WAV per name plus source, author, license, and attribution metadata. Names are lowercase, matched case-insensitively against `{name}` in Scripts.
- **Freesound client:** search and download only; used solely by the Sound library's add flow. The API key comes from a local config file or environment variable, never from the repo. Generation never calls it (ADR `docs/adr/0001-local-sound-library.md`).
- **Engines:** three narrow interfaces, each with a real implementation and a fake for tests:
  - Voice design engine: description + text → WAV. Real implementation is VoxCPM2 or Qwen3-TTS VoiceDesign, chosen after the spikes in `spikes/`.
  - Speech engine: text + Reference clip + exaggeration + cfg → WAV. Also used to produce Emotion preset Reference clips from the neutral clip, unless the consistency spike picks the design engine's style-cloning instead (see Pending on spikes). Real implementation is Chatterbox via chatterbox-mlx, hybrid-mlx backend, using the long-text path above about 50 words. Emotion presets store Chatterbox's values directly (ADR `docs/adr/0002-emotion-presets-store-chatterbox-settings.md`).
  - Vocal-effect engine: effect name + Reference clip → WAV, plus a list of supported effect names. v1 ships an implementation that supports no effects; Chatterbox Turbo is plugged in only if it passes its spike, translating `(laugh)` into Turbo's `[laugh]`. Turbo comes from a second package, `chatterbox-tts`, which shares the `chatterbox` import namespace with chatterbox-mlx; if they can't coexist in one environment, Turbo runs in its own environment as a subprocess.
- **Model manager:** guarantees at most one large model is loaded at a time. Chatterbox loads once at startup and stays loaded (`docs/design.md` section 6). When the voice design or vocal-effect engine is needed, the manager unloads Chatterbox, loads that engine, and reloads Chatterbox afterwards.
- **Generator:** runs the checker, then renders each Segment through the right engine or the Sound library, and hands the pieces to the assembler. Reports progress (current Segment, total).
- **Assembler:** stitches Segment audio in order with short gaps (a short crossfade where a gap sounds abrupt; exact lengths are tuned by ear), normalizes volume across Segments, and writes one WAV. Sound effects play in sequence only.
- **Output store:** the temporary Output cache (last N, setting 5–10, oldest evicted, cleared on startup) and the saved folder (never cleaned). Saving copies the WAV and writes a sidecar JSON with Script text, Voice name, the preset values used per emotion, and a credits list of every Sound effect used (name, source URL, author, license).
- **HTTP API:** FastAPI app. It starts from the draft endpoints in `docs/design.md` and must cover every user story; endpoint groups are:
  - Draft voices: design, list, get, regenerate neutral, regenerate one preset, retune one preset, edit description and regenerate, accept (with name), discard.
  - Voices: list, get, add preset, regenerate preset, retune preset, accept or reject a pending take, remove preset, delete Voice.
  - Sounds: list, search Freesound, add from a Freesound result under a name, replace the sound behind a name, remove.
  - Scripts: check (synchronous), generate (starts a job).
  - Jobs: status and progress, result.
  - Outputs: list the cache, play/download, save; list and download Saved outputs.
  - Convert: standalone file conversion.
  - Settings: read and change the Output cache size (5–10).
  - Serves the web page and every audio file.
- **Web page:** a single local page with Voices, Sounds, and Scripts areas. It talks only to the HTTP API.

### Contracts and behavior

- The HTTP API's request and response models (Pydantic) are the one contract between the page and the backend. Both live in this repo and change together, so no separate schema is needed.
- A rejected Script returns HTTP 422 with a body listing `missing_emotions`, `missing_sounds`, and `parse_errors`; a ready Script's response includes `warnings` (e.g. skipped Vocal effects).
- Long operations (voice design, preset generation, Script generation) run as one background job at a time. Generate runs the Script check synchronously first: a rejected Script returns 422 and no job is created. Otherwise it returns a job id; the page polls a status endpoint for progress and the result. Starting a second job while one runs returns HTTP 409.
- Model load failures and out-of-memory errors end the job with a readable error; the app stays up.
- Accepting a Draft voice under an existing Voice name returns HTTP 409.
- Freesound search or download fails with HTTP 503 and a reason (`no_api_key` or `unreachable`); the rest of the app keeps working.
- Sound names are lowercase and matched case-insensitively against `{name}`.
- Settings (Output cache size, Freesound API key, app data folder) live in a local config file outside git; the API key can also come from an environment variable.
- On startup: clear the Output cache, keep the draft area, and report surviving Draft voices so the page can offer resume or discard.
- Storage lives in one app data folder outside the repo (configurable), with subfolders for voices, drafts, sounds, cache, and saved.
- One command starts the backend and opens the page in the default browser.
- The README leads with a short demo (screenshot of the page and a sample Output) once v1 works.

### Pending on spikes

- Which voice design engine ships (VoxCPM2 or Qwen3-TTS) is decided by `spikes/test_voxcpm_design.py` and `spikes/test_qwen_design.py`. If neither runs acceptably on the M2, v1 instead creates a Voice from an uploaded recording passed through the Audio converter. In that case stories 1, 2, 6, and 7 become: upload a recording, trim it to about 15 seconds of clean speech as the neutral Reference clip, and re-upload to try again. Everything after the neutral clip is unchanged.
- How Emotion preset Reference clips are produced is decided by the consistency spike (`spikes/test_voxcpm_design.py`, `spikes/test_chatterbox_clone.py`): either Chatterbox from the neutral clip with the preset's values, or VoxCPM2's style-cloning from the neutral clip. Either way, Script generation always uses Chatterbox with the preset's clip and values.
- Whether Vocal effects render in v1 is decided by `spikes/test_turbo_effects.py`.

## Testing Decisions

- Good tests check behavior a user or the page can observe through the API (status codes, response bodies, files they can fetch, what's listed after an action), never internal function calls or file layout.
- **One seam: the HTTP API.** Tests drive the FastAPI app in-process with FastAPI's test client, against a fresh temporary app data folder per test.
- The voice design, speech, and vocal-effect engines and the Freesound client are replaced with fakes at their interfaces. Engine fakes return short fixed WAVs (distinguishable per call, e.g. by length or tone) so tests can assert which emotion preset or sound landed where in the Output. The Freesound fake returns canned search results and a small audio file in a non-WAV format so conversion is exercised.
- Covered through the seam: Script parsing and checking (every rejection and warning case), Freesound errors (no key, unreachable), the cache-size setting, the Voice and Draft voice lifecycle including restart survival and neutral-clip lock, preset add/retune/remove with review, Sound library add/replace/remove with license metadata, Output cache eviction and startup clearing, saving with sidecar contents and credits, one-job-at-a-time, and converter format handling.
- Real models get a separate slow smoke test, run by hand on the M2 and excluded from the default test run: design one Voice, render one short tagged Script, and check that a WAV of plausible length comes out without errors.
- The web page gets a manual click-through QA pass, not automated browser tests.
- Prior art: none in the codebase yet. The scripts in `spikes/` are the reference for how each real engine is called.

## Out of Scope

- Multiple Voices or Characters in one Script.
- Creating a Voice from an uploaded recording, unless the voice-design spike fails (then it replaces description-based design in v1).
- Sound effects that overlay speech (ambience, ducking).
- Generated sound effects (Stable Audio Open).
- Adding more emotions to the Default emotion set from the UI, or saving a Voice's custom emotion into the Default emotion set.
- Per-line exaggeration/cfg overrides inside a Script.
- A Re-render action from a Saved output's sidecar.
- Replacing a saved Voice's neutral Reference clip.
- Multiple sound files per name, or random variation between them.
- MP3 export.
- Languages other than English.
- Automated browser tests.

## Further Notes

- Content policy from `docs/design.md`: Voices are designed or recorded with consent; the app is not for cloning real people without permission.
- Freesound licenses vary per sound; the credits in Saved output sidecars exist so outputs can be shared with correct attribution.
- The Python environment must be 3.11 or 3.12 (chatterbox-mlx requires below 3.13).
- The real speech model uses about 14–16GB, which is why the one-model-at-a-time rule and one-job-at-a-time rule exist.
