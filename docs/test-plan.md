# Test Plan — Voicewright

**Issue:** #46 · **Status:** done · **Written:** 2026-11-18

## Where things stand

- **Python unit/API tests:** strong. `tests/` has 19 pytest files covering the app routes, CLI, conversion, drafts, design and editing of voices, jobs, generation, output cache, saved outputs, script checking, the sound library and the Freesound client. They run on fake engines (`tests/fakes.py`), and real-model smoke tests are run by hand (`pytest -m smoke -s`).
- **Front end:** none. The page's JavaScript (`static/common.js`, `voices.js`, `sounds.js`, `scripts.js`, `convert.js`, about 1,450 lines) has no tests.
- **End-to-end:** none. `docs/qa-v1.md` and the `docs/phase N test.md` files record manual click-through passes; those are the flows to automate.

## Goal

Browser E2E tests for every user-facing flow, plus unit tests for the front-end logic, per `CLAUDE.md`. Every test runs on the fake engines; none loads a real model or calls Freesound.

## Tooling

| Layer | Tool | Location | Command |
|---|---|---|---|
| Python unit/API | pytest (existing) | `tests/` | `pytest` |
| E2E | Playwright for Python (`pytest-playwright`) | `tests/e2e/` | `pytest tests/e2e` (marked `e2e`) |
| Front-end unit | Covered by E2E, see below | | |

Playwright for Python keeps the project single-language and reuses `tests/fakes.py` and the fixtures. Claude asks Bob before adding `pytest-playwright` to the `dev` extras.

**Front-end unit tests:** the JS files attach to `window.Voicewright` and aren't modules, so unit-testing them needs either a JS toolchain (Vitest + jsdom) or turning them into ES modules. Recommendation: cover the front end through E2E for now, and pull out pure helpers (script tag highlighting, time formatting, error-message building) into `common.js` functions that Playwright can call through `page.evaluate`. **Bob decides** whether to add a Node toolchain later.

**How E2E runs the app:** a pytest fixture starts `uvicorn` on a free port with `create_app(config_path, engines=fake_engines, freesound=fake_freesound)` and a temp data folder, so each test session starts empty. Fake engines return short generated WAVs, so jobs finish in milliseconds.

## E2E tests to write

1. `test_first_run.py`: an empty data folder shows the first-run state; settings can be saved.
2. `test_voices.py`
   - Describe a voice, start design, watch the job bar finish, review the Reference and Emotion clips.
   - Regenerate a preset, retune exaggeration/cfg, go back to an earlier take, accept.
   - Save the Voice under a name; it appears in the list; delete it (confirm dialog).
   - Discard a draft.
3. `test_sounds.py`: search (fake Freesound), preview a result, check the license, add it to the library, rename it, delete it.
4. `test_scripts.py`
   - Type a tagged Script with `[angry]` and `{thunder}`; the checker flags an unknown emotion and an unknown sound.
   - Generate; the Output plays; save it; it appears under Saved with its record.
5. `test_convert.py`: upload an audio file and download the converted WAV.
6. `test_jobs.py`: only one job runs at a time; the job bar shows progress and errors (a fake engine set to fail).
7. `test_errors.py`: a 503 from a missing model shows the plain-sentence error from `common.js`.
8. `test_layout.py`: the page at a narrow viewport (the app is a PWA).

## Unit-test gaps (Python)

1. `model_manager.py`: loading, unloading and the "model not installed" path, with fakes.
2. `assembler.py`, `wav.py`, `data_folder.py`: direct tests if any branch isn't already reached through the route tests (check with `pytest --cov` first).

## Order of work

1. Claude runs `pytest --cov=voicewright` and lists uncovered lines.
2. Claude adds `pytest-playwright` and the live-server fixture.
3. Claude writes the E2E tests, voices first (the biggest flow).
4. Claude fills the Python coverage gaps found in step 1.
5. Claude updates `CLAUDE.md` with the E2E command.

## Done when

- `pytest` (unit) and `pytest tests/e2e` (E2E) pass on the fakes.
- Every flow in `docs/qa-v1.md` has an automated equivalent.

## As built (2026-11-18)

- **Results:** `pytest` runs 400 unit tests and `pytest tests/e2e` runs 66 browser tests. All pass on the fakes. Coverage went from 191 missed lines to 179 (92%), and `model_manager.py`, `assembler.py` and `data_folder.py` are now at 100%.
- **Harness:** `tests/e2e/conftest.py` runs the app under uvicorn on a free port for each test, with a fresh data folder, the fake engines and the fake Freesound. The browser can only reach that server: Freesound preview clips are served from `tests/fixtures/tone.ogg`, and every other request is refused. A JavaScript error on the page fails the test. `Held` (in `tests/e2e/helpers.py`) pauses a fake engine call so a test can check the job bar while a job runs.
- **Running it:** a plain `pytest` skips `tests/e2e` (see `pytest_ignore_collect` in `tests/conftest.py`). Run the browser tests by naming the folder or a file in it. One-time setup: `.venv/bin/playwright install chromium`.
- **Bug found:** after replacing a sound, its "Replaced {name}" confirmation never appeared (#47). Fixed in `static/sounds.js`.

### Changes from the plan

- `tests/e2e/` is a package (it has an `__init__.py`), so its files can share names with the unit tests (`test_convert.py`, `test_jobs.py`, `test_first_run.py`).
- **First run:** the page has no separate first-run screen. `test_first_run.py` checks that every area starts empty, and that the one setting the page offers (how many recent Outputs to keep) is saved to the config file.
- **Sounds:** a sound can't be renamed. The tests cover Replace (same name, different sound) instead.
- **Errors:** a missing model doesn't give a 503. It ends the job with an error, which shows beside the Design form. The 503 path is covered by Freesound with no API key. `test_errors.py` also covers a dropped connection and a 500 with no detail.
- **Front-end unit tests:** nothing was pulled out of the JS. Every helper the plan named (tag highlighting, error sentences, time and length formatting) is checked through the page. Bob still decides whether to add a Node toolchain.

### qa-v1 stories and their automated checks

| Stories | Where |
|---|---|
| 1-11, 14-25 (design, review, takes, accept, discard, edit saved Voices) | `tests/e2e/test_voices.py` |
| 12-13 (Draft voices survive a restart; resume or discard) | a page reload in `test_voices.py`; the server restart in `tests/test_accept_discard.py` and `tests/test_review_draft.py` |
| 15, 48, 49 (progress, one job at a time) | `tests/e2e/test_jobs.py`, `test_voices.py` |
| 26-34 (search, preview, license, add, replace, remove) | `tests/e2e/test_sounds.py` |
| 35, 60 (Freesound unavailable, model failures) | `tests/e2e/test_errors.py`, `test_jobs.py` |
| 36-44, 46-47, 50-53, 55 (Scripts, check, generate, Outputs, save, download) | `tests/e2e/test_scripts.py`, `test_first_run.py` |
| 54 (Outputs cleared at startup) | `tests/test_output_cache.py` (needs a server restart) |
| 56 (convert) | `tests/e2e/test_convert.py` |
| 45, 58, 59 (long passages, one model in memory, offline) | real-model smoke tests (`pytest -m smoke -s`), and `tests/test_model_manager.py` for 58 |
| 57, 61 (one-command start, README) | `tests/test_cli.py`, plus the manual checklist and review |
| Phone-width layout, area addresses, theme, install manifest | `tests/e2e/test_layout.py` |
