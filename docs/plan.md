# Voicewright v1 build plan

Spec: #1 ([`docs/spec-v1.md`](spec-v1.md)). Design: [`docs/design.md`](design.md).

Each step is one GitHub issue and a sub-issue of #1. `ready-for-agent` steps can be picked up by an agent; `ready-for-human` steps need someone at the M2. Work on a step logs to `DevNotes/Logs/phase-N.md` under `## Phase N.M`.

## Phases

### Phase 0 — Design and spikes

Goal: settle the design and find out which models work on the M2 before building on them. Steps 0.1 (design grilling) and 0.3 (spec and this plan) are done and have no issues.

Done when: the spike results and the three model decisions are in `docs/design.md`, and the upload fallback is marked active if no voice-design engine passes.

### Phase 1 — Foundation

Goal: a running FastAPI app with config, a data folder, the audio converter, a one-at-a-time job runner, engine interfaces with fakes, and the real Chatterbox speech engine.

Done when: one command starts the app and opens the page, `pytest` runs against a temporary data folder with every engine faked, and the smoke test renders a 120-word passage on the M2.

### Phase 2 — Voices

Goal: design a Draft voice from a description, review it, accept or discard it, and edit saved Voices, through the API and the page.

Done when: a Draft voice gets every preset in the Default emotion set, survives a restart, can be accepted under a unique name, and the whole Voice flow works in the browser.

### Phase 3 — Sound library

Goal: a local Sound library filled by searching Freesound, with license metadata stored for every sound.

Done when: a Freesound result is added as a standard WAV with its license, both 503 reasons are tested, and the Sound flow works in the browser.

### Phase 4 — Scripts and Outputs

Goal: check a tagged Script, render it into one Output, keep recent Outputs in a cache, and save Outputs with sidecar records.

Done when: the check reports every problem in one request, a rejected Script starts no job, Outputs contain the right clips in order, saved Outputs survive eviction and restart, and the Script flow works in the browser.

### Phase 5 — Finish v1

Goal: vocal effects if the spike passed, a full offline smoke test, a manual QA pass, and a README demo.

Done when: the smoke test passes on the M2 with Wi-Fi off, every user story is checked with bugs filed, and the README opens with the demo.

## Steps

| Step | Issue | Title | Label | Blocked by |
|---|---|---|---|---|
| 0.2 | #2 | Run the model spikes and record results | `ready-for-human` | None |
| 1.1 | #3 | Project skeleton, config, and test harness | `ready-for-agent` | None |
| 1.2 | #4 | Audio converter and convert endpoint | `ready-for-agent` | #3 |
| 1.3 | #5 | Job runner, engine interfaces, and model manager | `ready-for-agent` | #3 |
| 1.4 | #6 | Chatterbox speech engine | `ready-for-agent` | #5 |
| 2.1 | #7 | Default emotion set | `ready-for-agent` | #3 |
| 2.2 | #8 | Design a Draft voice | `ready-for-agent` | #2, #6, #7 |
| 2.3 | #9 | Review a Draft voice | `ready-for-agent` | #8 |
| 2.4 | #10 | Accept, discard, and resume Draft voices | `ready-for-agent` | #9 |
| 2.5 | #11 | Edit a saved Voice | `ready-for-agent` | #10 |
| 2.6 | #12 | Voices area of the page | `ready-for-agent` | #11 |
| 3.1 | #13 | Sound library storage | `ready-for-agent` | #4 |
| 3.2 | #14 | Freesound search and add | `ready-for-agent` | #13 |
| 3.3 | #15 | Sounds area of the page | `ready-for-agent` | #14 |
| 4.1 | #16 | Script parsing and checking | `ready-for-agent` | #10, #13 |
| 4.2 | #17 | Generate and assemble an Output | `ready-for-agent` | #6, #16 |
| 4.3 | #18 | Output cache and cache setting | `ready-for-agent` | #17 |
| 4.4 | #19 | Save Outputs with sidecar records | `ready-for-agent` | #18, #14 |
| 4.5 | #20 | Scripts area of the page | `ready-for-agent` | #19, #12 |
| 5.1 | #21 | Chatterbox Turbo vocal effects (only if 0.2 passed) | `ready-for-agent` | #2, #17 |
| 5.2 | #22 | Full real-model smoke test | `ready-for-human` | #19 |
| 5.3 | #23 | Manual QA pass of the page | `ready-for-human` | #20 |
| 5.4 | #24 | README demo | `ready-for-agent` | #22 |
