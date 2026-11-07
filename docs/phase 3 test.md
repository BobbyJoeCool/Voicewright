# Phase 3 test: what to test by hand

> Run on 2026-11-07, filled in, and passed. Part A rechecks the phase 2 Voices fixes (#37) on the real models; Part B is the phase 3 Sounds click-through (#15). Results are posted on #37 and #15.

Two things need you at the Mac before they can close. Fill in this file as you go, then tell
me. I'll analyze it, post the results to the issues, file bugs for anything that failed, and
close what passed.

| Part | Issue | What | Needs | Time |
| --- | --- | --- | --- | --- |
| A | #37 | Recheck the Voices page fixes on the real models | The models (already installed) | ~10 min |
| B | #15 | Click through the new Sounds area on the real Freesound | A free Freesound API key | ~15 min |

## How to record results

- Each step lists what you should see as checkboxes. Tick `[x]` each one that happened.
- Leave a box unticked if it didn't happen, and say what you saw instead in that step's
  **Notes** line. Copy any error text exactly: from the page, the terminal, or a dialog.
- If a step can't be done because an earlier one failed, write `SKIPPED (A? failed)` or
  `SKIPPED (B? failed)` in its Notes.

## Before you start

Both parts run from the phase 3 branch, which has the #37 fixes and the Sounds area. Check
you're on it:

```bash
cd ~/csd/Side-Projects/Voicewright
git switch feat/sound-library
```

Get a Freesound API key for Part B now, but **don't put it in the config yet**: B1 checks
the message you get without one.

1. Sign in at <https://freesound.org> (or sign up).
2. Go to <https://freesound.org/apiv2/apply>, fill in the short form (any name and
   description, e.g. "Voicewright, a local app"), and copy the **Client secret/Api key**.

Then start the app and keep the terminal visible:

```bash
.venv/bin/voicewright
```

## Part A — Voices page fixes on the real models (#37)

These were checked on fake models only. The real models are slower, and real audio is long
enough to tell whether it plays by itself.

### A1 — Startup bar

When the page opens, watch the blue bar while the speech model loads.

- [x] The bar goes away when loading ends
- [x] **Design** is enabled once it does (last time this box was left unticked)

**Notes:**

### A2 — Step counter

Design a voice, e.g. `A gravelly older man with a slow, calm, warm voice.` Watch the bar
to the end.

- [x] It counts step 1 of 4 up to step 4 of 4, and never shows "step 5 of 4"
- [x] The last message, "Reloading the speech model", has no step number

**Notes:**

### A3 — New takes play by themselves

In the review card:

1. Click **Regenerate** on **angry**.

   - [x] When it finishes, the new angry take starts playing without you pressing play

2. On **sad**, move the sliders and click **Hear these values**.

   - [x] When it finishes, the preview starts playing by itself and scrolls into view

**Browser used (Chrome, Safari, …):** Chrome

**Notes:**

### A4 — Errors show next to the button

At **Save to your Voices**, type a few spaces as the name and click **Accept**.

- [x] The red error shows just below **Accept**, not at the top of the page
- [x] The review card stays as it was (it doesn't reload)

Now name it `Test Voice` and click **Accept**.

- [ ] It's saved and appears under **Saved Voices**

**Notes:**

### A5 — The saved Voice card stays open

Open **Test Voice**'s card.

1. On **sad**, move the sliders and click **Hear these values**.

   - [x] The card stays open when the job finishes
   - [x] The new take in the yellow box plays by itself
   - [x] Click **Accept**: the card stays open

2. On **excited**, click **Regenerate**.

   - [x] The card stays open and the new clip plays by itself
   - [x] Click **Reject**: the card stays open

3. In **Add an Emotion preset**, type `Bad Name` and click **Design it**.

   - [x] A red error shows under the form, the card stays open, and `Bad Name` is still in
     the box

4. Change the name to `whisper` and click **Design it**.

   - [x] The card stays open and the whisper take plays by itself

**Notes:** The new yellow box appears at the bottom of the page instead of underneath sad.  It should show up right under Sad instead of having to scroll to the bottom of the established emotions, or be a popup.

Delete Test Voice afterwards if you like (**Delete Test Voice**).

## Part B — Sounds area on the real Freesound (#15)

### B1 — Search with no API key (story 35)

In **Sounds → Find a sound on Freesound**, search for `thunder`.

- [x] A red message says searching Freesound needs an API key, and names your config file
- [x] It has a **Get a Freesound API key** link that opens the sign-up page
- [x] The rest of the page (Voices, Convert) still works

**Notes:**

### B2 — Add your key, without restarting

Open `~/.config/voicewright/config.toml` and set `freesound_api_key = "your key"` (in
quotes). Save it. **Don't restart the app.** Search for `thunder` again.

- [x] Results appear, with a count like "N results for "thunder" on Freesound"
- [x] Each result shows its title, author, length, an "on Freesound" link, and a License
  line with a short note on what it asks (credit, non-commercial, or no credit needed)

**Notes:**

### B3 — Preview and page through (stories 27, 28)

- [x] Each result's player plays the sound
- [x] **More results** loads more below, without losing the first ones
- [x] An "on Freesound" link opens the sound's page

**Notes:**

### B4 — Add a sound under a name (stories 29, 30, 31)

Pick a short thunder result. In its name box (pre-filled with `thunder`), keep `thunder` and
click **Add**.

- [x] The button says "Adding…" briefly, then "Added as {thunder}." shows under the result
- [x] **{thunder}** appears under **Your Sound library**, with its title, author, license,
  length, and an "on Freesound" link
- [x] Its player plays, and it sounds like the preview did

**Seconds from click to "Added":** about 5

**Notes:**

### B5 — A taken name and a bad name

On a different result, try to add it as `Thunder` (capital T).

- [x] A red line under that result says the library already has {thunder}

Now try the name `big thunder` (with a space).

- [ ] A red line says it can't be a sound name, and explains the rule

**Notes:**

### B6 — Replace the sound behind a name (story 33)

Click **Replace** on {thunder} in the library.

- [x] A yellow bar says to pick a result to replace {thunder}, with **Cancel**
- [x] Each result's button now says **Replace {thunder}** (and has no name box)

Click **Replace {thunder}** on a different result.

- [x] {thunder} keeps its name, but now shows the new sound's title, author, and license
- [x] Its player plays the new sound
- [x] The yellow bar goes away and the buttons say **Add** again

**Notes:**

### B7 — Remove a sound (story 34)

Click **Remove** on {thunder}.

- [x] A confirm dialog warns that Scripts using it won't run until it's added again
- [x] After OK, it's gone, and "No sounds yet." shows (if it was your only one)

**Notes:**

### B8 — Survives a restart (story 32)

Add any sound again (e.g. search `door slam`, add as `door-slam`). Stop the app with
**Ctrl+C** and start it again.

- [x] {door-slam} is still in the library and plays

**Notes:**

## Wrap-up

- [x] No errors or tracebacks in the terminal during either part (paste any below)
- [x] The page never froze or got stuck with the job bar showing

**Terminal errors (paste):**

```text
```

**Anything confusing, slow, or annoying, even if it worked:** Not really.  Since I would like this to be a standalone web app (outside of a browser window), it might be best to have the popup confirm dialogs be designed at some point rather than relying on the browser version.  Or is that not going to be possible?

**Part A: do the Voices fixes work on the real models? (yes / no / yes with issues):** Yes

**Part B: does the Sound flow pass? (yes / no / yes with issues):** Yes
