# v1 QA pass

Step 5.3 (#23): every user story in [`spec-v1.md`](spec-v1.md) checked against the running app. Run on 2026-11-13 on the M2 (24 GB), at version 1.0.0.

## How it was run

- **Browser:** a script drove the page in headless Chrome over the DevTools protocol. It clicked the same buttons a person would and checked what the page showed and what the API returned. It ran against the real app (`voicewright --tab`) with the real models, a temporary data folder, and the real Freesound API. It also restarted the app partway through to check that Draft voices survive and that Outputs are cleared on startup. No JavaScript errors were logged during the run.
- **Smoke test:** `.venv/bin/pytest -m smoke -s`. All 5 passed, including the new full smoke test (step 5.2) described below.
- **Unit tests:** `.venv/bin/pytest`. All 380 passed.
- **Manual:** the 5.5 checklist, run by hand: the app-window launch, installing it, the dialogs' keyboard behavior, how typing feels in the editor, and drag and drop. All passed.

The automated checks cover lengths, formats, order, and playback, not how the audio sounds. Listen to the sample Output in [`media/`](media/) to judge that.

## Smoke test (step 5.2, #22)

`tests/smoke/test_full_smoke.py` adds a sound from Freesound, then goes offline. From then on it refuses every connection that isn't to this machine and sets `HF_HUB_OFFLINE=1`. Offline, it designs a Voice, accepts it, renders a tagged Script with an emotion change and the sound, and saves the Output. It samples macOS memory pressure (`kern.memorystatus_vm_pressure_level`) once a second the whole time.

| Run | Design → render → save | Output | Worst memory pressure |
| --- | --- | --- | --- |
| 1 | 94 s | 22.9 s | warning (yellow), 85 samples |
| 2 | 92 s | 23.1 s | warning (yellow), 83 samples |

Memory pressure stayed out of the red, even through the swap from Chatterbox to Qwen3-TTS and back. The offline check refuses connections in-process instead of turning Wi-Fi off; turning Wi-Fi off too is the stricter check. Run 1's Output is the README's sample.

## Results

61 of 61 stories pass. No bugs were found, so none were filed.

| # | Story | Checked by | Result | What was seen |
| --- | --- | --- | --- | --- |
| 1 | Describe a voice in plain words (e.g. "gravelly older man, slow and calm") | Browser | Pass | designed a Draft voice from the description "A gravelly older man with a slow, calm, warm voice." |
| 2 | The app to generate a neutral Reference clip of about 15 seconds from my description | Browser | Pass | neutral Reference clip is 17.3s |
| 3 | The app to generate one Emotion preset for each emotion in the Default emotion set, designed from my description plus the emotion | Browser | Pass | 4 presets designed, none missing |
| 4 | Play each clip of a Draft voice in the page | Browser | Pass | 4 players in the review; every clip is WAV; the first played 0.76s |
| 5 | Regenerate a single Emotion preset without regenerating the others | Browser | Pass | after Regenerate on angry, changed presets: angry |
| 6 | Regenerate the neutral clip while the Voice is still a Draft voice | Browser | Pass | neutral take neutral-1 → neutral-2 |
| 7 | Edit the description of a Draft voice and regenerate | Browser | Pass | description is now "A gravelly older man with a slow, calm, warm voice, a little hoarse.", every preset redesigned |
| 8 | Adjust an Emotion preset's exaggeration and cfg values and hear the result | Browser | Pass | review shows "Spoken at exaggeration 0.9, cfg 0.2"; sad preset now 0.9/0.2 |
| 9 | Accept a Draft voice under a name I choose | Browser | Pass | accepted as QA Narrator; it's in Saved Voices and the draft is gone |
| 10 | Discard a Draft voice | Browser | Pass | dialog "Discard this Draft voice?"; Escape kept it: true; Enter (Cancel focused) kept it: true; backdrop click kept it: true; Discard removed draft cfbc34722cff46e3b1909980157bf5d0 |
| 11 | Every clip I generate while reviewing a Draft voice to stay available until I accept or discard it | Browser | Pass | angry takes angry-1, angry-2 all still play; chose angry-1 back from the Take list |
| 12 | My Draft voices to survive an app restart or crash | Browser | Pass | the Draft voice is still there after stopping and restarting the app |
| 13 | The app to offer to resume or discard each surviving Draft voice when it starts | Browser | Pass | after restart the Voices area offers: Resume, Discard; Resume reopened the review |
| 14 | Be told clearly if I try to accept a Voice name that already exists | Browser | Pass | accepting as "qa narrator" said: "A Voice named QA Narrator already exists; pick another name." |
| 15 | The page to show that a voice is being generated and roughly which step it's on | Browser | Pass | job pill showed: Loading the voice design model (step 1 of 4) / Designing the neutral clip (step 1 of 4) / Designing the angry preset (step 2 of 4) / Designing the sad preset (step 3 of 4) |
| 16 | See a list of my saved Voices | Browser | Pass | Saved Voices lists QA Narrator; sidebar badge 1 |
| 17 | See which Emotion presets a Voice has | Browser | Pass | card chips: neutral, angry, sad, excited |
| 18 | Play any saved Emotion preset | Browser | Pass | every saved preset has a player and its clip plays as WAV |
| 19 | Add a new Emotion preset (e.g. `angry-soft`) to a saved Voice by giving it a name, an optional sample sentence, and starting values | Browser | Pass | added angry-soft with a sample sentence; pending: "New angry-soft clip. Keep it?AcceptReject"; accepted |
| 20 | A new or regenerated Emotion preset on a saved Voice to go through the same listen-and-accept review | Browser | Pass | the new preset wasn't in the Voice until accepted; a rejected retune left angry at 0.7/0.3 |
| 21 | Retune an existing Emotion preset's values | Browser | Pass | retuned and accepted: angry is now 1/0.25 |
| 22 | Remove any Emotion preset except neutral from a saved Voice | Browser | Pass | "Remove excited?" removed excited; neutral has no Remove button and DELETE is refused (409) |
| 23 | The neutral Reference clip and the description of a saved Voice to be locked | Browser | Pass | page shows "The neutral clip is locked." with no Regenerate, and no description editor; the API refuses regenerating neutral (409) |
| 24 | Delete a saved Voice | Browser | Pass | Delete QA Narrator (confirmed) removed it; the empty-state message is back |
| 25 | New Voices to start with the Default emotion set (at least neutral, angry, sad, excited) | Browser | Pass | Draft emotions: neutral, angry, sad, excited |
| 26 | Search Freesound from inside the app | Browser | Pass | searched Freesound from the page: "2025 results for "door creak" on Freesound." |
| 27 | Preview Freesound results before picking one | Browser | Pass | 15 results each with a preview player; the first played 1.16s |
| 28 | See each result's license before picking it | Browser | Pass | every result shows its license, e.g. License: Attribution 4.0 |
| 29 | Save a picked sound under a name I choose | Browser | Pass | added the first result as {creak}; page says "Added as {creak}." |
| 30 | Picked sounds converted to the app's standard WAV format automatically | Browser | Pass | the library copy is WAV, 1 channel, 16-bit (from Freesound's OGG preview) |
| 31 | Each Sound library entry to keep its source, author, and license | Browser | Pass | kept credit: `"DoorCreaking11.flac" by Zabuhailo (https://freesound.org/people/Zabuhailo/sounds/214082/), licensed under Attribution 4.0` |
| 32 | List and play the sounds in my Sound library | Browser | Pass | the library lists {creak} with a player that plays (0.76s); sidebar badge 1 |
| 33 | Replace the sound behind a name | Browser | Pass | {creak} now Freesound 214081 (was 214082); the name stayed |
| 34 | Remove a sound from the library | Browser | Pass | "Remove {creak}?" → Remove took it out of the library |
| 35 | A clear message when Freesound can't be reached or my API key is missing | Browser | Pass | with no key the page says "Searching Freesound needs an API key. Get one at <https://freesound.org/apiv2/apply>, then put it in the config file as freesound_api_key (or the FREESOUND_API_KEY environment variable). Get a Freesound API key" and the rest of the app answers; bad key and unreachable are covered by tests/test_freesound_client.py and the 503 tests |
| 36 | Pick one saved Voice for a Script | Browser | Pass | picked QA Narrator in the Voice list; the palette offers its emotions: [neutral] [angry] [sad] [angry-soft] |
| 37 | Write `[emotion]` to change emotion until the next Emotion tag | Browser | Pass | [angry] and [sad] switch emotion: speech:neutral, sound_effect:thunder, speech:angry, vocal_effect:sigh, speech:sad |
| 38 | Untagged text to use the neutral preset | Browser | Pass | untagged first line is neutral speech |
| 39 | Write `{name}` to place a Sound effect between speech | Browser | Pass | {thunder} is a Sound effect Segment in order after the first line |
| 40 | Write `(name)` to place a Vocal effect | Browser | Pass | (sigh) parses as a Vocal effect |
| 41 | The app to check the whole Script before generating and list every Emotion tag the Voice lacks | Browser | Pass | Check listed: [furious] QA Narrator has no furious preset. Add furious to QA Narrator / {thunder} isn't in your Sound library. Find it on Freesound / Line 2, column 1: This [ is never closed: a Emotion tag ends with ] on the same line, like [angry]. / Line 1, column 45: (gasp) is skipped: Vocal effects can't be rendered yet. |
| 42 | The same check to list every Sound effect name missing from the Sound library, each with a way to search Freesound for it | Browser | Pass | {thunder} was listed as missing with "Find it on Freesound", which opened Sounds, searched, and offered the name "thunder"; added it |
| 43 | Unsupported Vocal effects reported as warnings and skipped, rather than rejecting the Script | Browser | Pass | (gasp) is listed as a warning, not a problem |
| 44 | Malformed tags (e.g. an unclosed `[angry`) reported with their position | Browser | Pass | the unclosed [sad is reported with its line and column |
| 45 | Long passages of speech to render without cutting off | Smoke test | Pass | see tests/smoke/test_speech_smoke.py: the 120-word passage renders without cutting off |
| 46 | The Output assembled as one WAV with short gaps between Segments and even volume | Browser | Pass | one 23.3s WAV; gaps and loudness levelling are checked by tests/test_generate.py (assembler) and by ear in the smoke Output |
| 47 | Play the Output in the page as soon as it's ready | Browser | Pass | ⌘Enter generated, and the new Output started playing at the top of Recent Outputs |
| 48 | The page to show generation progress (e.g. Segment 3 of 7) | Browser | Pass | job pill: Speaking “The storm had been building all…” (neutral) (Segment 1 of 4) / Speaking “I told you to bring the…” (angry) (Segment 3 of 4) / Speaking “Now half of them are out…” (sad) (Segment 4 of 4) |
| 49 | Be told if a generation is already running when I start another | Browser | Pass | while generating, Generate was disabled and a second start got 409: {"detail":"A script job is already running; wait for it to finish","running_job_id":"a522dfb21f784bdb89e552adc849485f"} |
| 50 | My last several Outputs (a setting from 5 to 10) kept temporarily | Browser | Pass | the page offers cache sizes 5 to 10; set 5; 5 Outputs kept after 6 generations |
| 51 | The oldest temporary Output removed automatically when the limit is reached | Browser | Pass | the oldest Output was removed automatically; its Saved copy stayed |
| 52 | Save an Output | Browser | Pass | Save copied it to Saved outputs and the card shows Saved |
| 53 | A Saved output to come with a record of the Script text, Voice, preset values, and credits and licenses for every Sound effect used | Browser | Pass | record has the Script, Voice, presets (neutral, angry, sad), and {thunder} Attribution 4.0 |
| 54 | Temporary Outputs cleared when the app starts | Browser | Pass | after a restart Recent Outputs is empty and the Saved output is still there |
| 55 | Download an Output or Saved output from the page | Browser | Pass | Download WAV links: qa-narrator-20261113-223410.wav, 2026-11-13-223412-qa-narrator-70a6e3.wav |
| 56 | Convert an audio or video file (MP3, M4A, FLAC, OGG, AAC, video audio) to the app's standard WAV | Browser | Pass | converted tone.m4a to 1-channel 16-bit WAV; player ready and download named tone.wav (every format is covered in tests/test_convert.py) |
| 57 | Start the app with one command and open it in my browser at a local address | Browser, manual checklist | Pass | one command served the page at <http://127.0.0.1:8799/> ("Voicewright"); the app-window launch itself was checked by hand with the 5.5 manual checklist |
| 58 | The app to keep only one large model in memory at a time | Smoke test, unit tests | Pass | see the 5.2 smoke test: memory pressure peaked at warning (yellow), never critical, through the swap; tests/test_jobs.py covers one model at a time |
| 59 | Generation to work with no internet connection | Smoke test | Pass | see the 5.2 smoke test: design, render, and save ran with every non-local connection refused and Hugging Face offline |
| 60 | The app to tell me plainly when a model fails to load or runs out of memory | Unit tests | Pass | covered by tests (model load failure and out-of-memory messages) in tests/test_jobs.py and tests/test_chatterbox_speech.py |
| 61 | The repo's README to show what the app does near the top | Review | Pass | README opens with a screenshot of the Scripts area and a link to a real, unedited Output (step 5.4) |

Two checks went beyond the stories:

- **Story 41:** the "Add furious to QA Narrator" button opened Voices with the Add an Emotion preset form already filled in.
- **Story 43:** an Output with `(sigh)` in its Script rendered with the effect skipped.
