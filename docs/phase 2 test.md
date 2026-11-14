# Phase 2 test: Voices area manual QA runbook (step 2.6)

> Run and filled in for #12. Its findings became #37 (fixed, rechecked in `phase 3 test.md` Part A), #38, and #39.

Issue: #12. Its one acceptance criterion: **a manual click-through of the whole Voice flow
works in the browser.** The automated run used fake engines. This one uses the real models
on the M2, so it is the only test of real audio quality and real wait times.

## How to record results

- Each step lists what you should see as checkboxes. Tick `[x]` each one that happened.
- Leave a box unticked if it didn't happen, and say what you saw instead in that step's
  **Notes** line. Copy any error text exactly: from the page's red error line, the
  terminal, or a dialog.
- If a step can't be done because an earlier one failed, write `SKIPPED (step N failed)`
  in its Notes.
- Times: a phone stopwatch is fine. Round to the nearest 10 seconds.

When you're done, save this file and tell me. I'll go through it, post a summary to #12,
open a bug issue for each failure, and close #12 if the flow passes.

## Before you start

- Close heavy apps. Open **Activity Monitor → Memory** and keep **Memory Pressure**
  visible.
- If `~/Voicewright` already holds Voices or drafts from earlier testing, note that here so
  I don't mistake them for new ones:

  **Existing data:**

- Start the app from the project folder:

```bash
cd ~/csd/Side-Projects/Voicewright
.venv/bin/voicewright
```

Keep that terminal visible: errors show up there.

## Step 1 — Startup and the job bar (story 15)

The browser opens at <http://127.0.0.1:8765/>.

- [x] The page opens, with a **Voices** section above **Convert**
- [x] A blue bar at the top shows the speech model loading, with a progress bar
- [x] While it shows, the **Design** button is disabled
- [ ] The bar goes away when loading ends, and **Design** is enabled again

**Load time (s):** about 5 seconds

**Notes:**. Page is very plain.  Styling needs to be done, but that can be later.  ALso should be more of a webapp feel rather than a Chrome window.

## Step 2 — Design a voice (story 15)

In **Describe the voice**, type:

> A gravelly older man with a slow, calm, warm voice.

Click **Design** and start the stopwatch.

- [x] The bar shows something like "Designing the neutral clip (step 1 of 4)"
- [x] The step number goes up as it works (2 of 4, 3 of 4, 4 of 4)
- [x] Buttons that start jobs are disabled while it runs
- [x] When done, a **Review the Draft voice** card opens with 4 presets: neutral, angry,
  sad, excited
- [x] The description box is cleared, and the draft also shows under **Draft voices**

**Design time, click to review card (s):** abuot 30-45 seconds.

**Peak Memory Pressure (green / yellow / red):** Yellow

**Notes:** There was a step 5/4 (Reloading the Speech Model).  THis should be corrected.  The emotion voices are all the same, but different from the original.

## Step 3 — Listen to the draft (story 4)

Play every clip in the review card.

- [x] All 4 clips play
- [x] neutral sounds like the description
- [x] angry, sad, and excited sound like that emotion
- [ ] All 4 sound like the **same man**
- [x] No hiss, clipping, cut-off words, or garbled audio

**Rate each clip 1 to 5 (5 = great), with a word or two on why:**

| Preset | Rating | Comment |
| --- | --- | --- |
| neutral | 5/5 | |
| angry | 4/5 | |
| sad | 4/5 | |
| excited | 4/5 | |

**Notes:** See above.  Emotions are great, but sound like a different person.

## Step 4 — Regenerate and go back to a take

1. On **angry**, click **Regenerate**. Time it.

   - [x] The bar shows the job, and the new take plays when it finishes
   - [x] A take chooser ("Take …") appears on angry

2. In the take chooser, pick the **first** take.

   - [x] The player goes back to the original angry clip

**Regenerate time (s):** 5 seconds.

**Notes:** The voice sounds very different in the second clip.

## Step 5 — Retune with the sliders

On **sad**, move **Exaggeration** to about **0.9** and **cfg** to about **0.2**, then click
**Hear these values**.

- [x] The numbers next to the sliders update as you drag
- [x] A job runs, and a preview with the new values plays afterward
- [x] The preview sounds different from the original sad clip (more intense)

**Retune time (s):** about 10 seconds

**Did the new values sound better or worse?** Nothing played.  I found the play bar underneath.  The preview is very different.

**Notes:** Thre is a sound artifact at the beginning. "KAI"

## Step 6 — Redesign from a new description

In the review card's **Description** box, change it to:

> A gravelly older man with a slow, calm, warm voice and a slight Southern drawl.

Click **Redesign every preset from this description**.

- [x] The bar shows all 4 steps again
- [x] Every preset gets a new clip with the drawl
- [x] Earlier takes are still in the take choosers (nothing was thrown away)

**Redesign time (s):** 15 seconds.

**Notes:**

## Step 7 — Resume after a restart

Leave the draft unsaved. In the terminal, press **Ctrl+C** to stop the app, then run
`.venv/bin/voicewright` again. Wait for the model load to finish.

- [x] The draft is listed under **Draft voices** with **Resume** and **Discard**
- [x] **Resume** opens the review card with the same clips, takes, and slider values as
  before the restart

**Notes:**

## Step 8 — Accept the draft (stories 16, 17)

At the bottom of the review card, under **Save to your Voices**, type the name
`Old Narrator` and click **Accept**.

- [x] The review card closes and the draft leaves **Draft voices**
- [x] **Old Narrator** appears under **Saved Voices**
- [x] Its collapsed card lists its presets: neutral, angry, sad, excited
- [x] Opening the card shows the description and each preset with its player

**Notes:**

## Step 9 — A duplicate name, then discard

Design a second voice, any description you like, for example:

> A bright young woman who talks fast.

When its review card opens, try to accept it under the name `old narrator` (all lower case).

- [x] A red error says the name is taken, and the draft stays open

Now find it under **Draft voices** and click **Discard**.

- [x] A confirm dialog asks before discarding
- [x] After OK, the draft is gone from the list and the review card closes

**Second design time (s):**

**Notes:** The error message is all the way at the top instead of next to the Accept button.  THis should be fixed.

## Step 10 — Play the saved Voice (story 18)

Open **Old Narrator** under **Saved Voices**.

- [x] Every preset plays
- [x] Each clip is the one the review card was playing for that preset just before you
  clicked **Accept** in step 8 (after the redesign, that's the drawl version)
- [x] **neutral** shows "The neutral clip is locked." with no **Regenerate** or **Remove**

**Notes:**

## Step 11 — Edit a saved preset: retune, then accept

On **sad** in Old Narrator, move the sliders somewhere new and click **Hear these values**.

- [x] A yellow box appears: "New values for sad: exaggeration …, cfg …. Keep it?" with a
  player
- [x] Click **Accept**: the box goes away and sad's sliders now show the new values
- [x] sad's clip itself didn't change (only the values did)

**Notes:** It closes the card when it finishes, that should be fixed.  It also closes that card when you click accept.

## Step 12 — Regenerate a saved preset, then reject

On **excited**, click **Regenerate**.

- [x] A yellow box appears: "New excited clip. Keep it?" with a player
- [x] Click **Reject**: the box goes away and excited still plays the old clip

**Notes:** Same as above.

## Step 13 — Add a custom preset, then remove it

In **Add an Emotion preset**, enter the name `whisper` and the sample sentence:

> Come closer. I don't want anyone else to hear this.

Click **Design it**.

- [x] A yellow box appears for the new whisper clip
- [x] It sounds like the same man, whispering or hushed
- [x] Click **Accept**: whisper now appears as a preset, and in the card's summary line

Now click **Remove** on whisper.

- [x] A confirm dialog asks first
- [x] After OK, whisper is gone from the card and the summary

**Add-preset time (s):**

**Notes:**

## Step 14 — Delete the Voice

This deletes Old Narrator. If you'd rather keep it, skip this step and write `SKIPPED
(kept it)` in the Notes.

Click **Delete Old Narrator**.

- [x] A confirm dialog asks first
- [x] After OK, the card is gone and "No saved Voices yet." shows (if it was your only one)

**Notes:**

## Wrap-up

- [x] No errors or tracebacks in the terminal during the run (if there were, paste them
  below)
- [x] The page never froze or got stuck with the job bar showing

**Terminal errors (paste):**

```text
```

**Worst Memory Pressure seen (green / yellow / red), and during which step:**. Yellow, during voice creation.

**Anything confusing, slow, or annoying about the page, even if it worked:** The voice card kept closing when you click accept or reject when adding emotions or adjusting them.

**Overall: does the Voice flow pass? (yes / no / yes with issues):** Yes with issues.  The voices are not exactly as close to each other as I would like, however, that might be an issue we approach later down the line.
