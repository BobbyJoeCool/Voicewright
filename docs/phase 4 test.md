# Phase 4 test: what to test by hand

Step 4.5 (#20) closes on one thing: **a manual click-through of the Script flow works in the
browser.** The automated runs used fake engines, which make short beeps. This run uses the
real models, so it's the only check of how a finished Output sounds. Fill this file in as
you go, then tell me. I'll post the results to #20, file bugs for anything that failed, and
close what passed.

| Part | What | Needs | Time |
| --- | --- | --- | --- |
| C | The Script flow, from check to saved Output | The models, and your Freesound key (already in the config) | ~25 min |
| D | Listening: how the Output sounds | Headphones help | ~5 min |

## How to record results

- Each step lists what you should see as checkboxes. Tick `[x]` each one that happened.
- Leave a box unticked if it didn't happen, and say what you saw instead in that step's
  **Notes** line. Copy any error text exactly: from the page, the terminal, or a dialog.
- If a step can't be done because an earlier one failed, write `SKIPPED (C? failed)` in its
  Notes.

## Before you start

This runs from the phase 4 branch:

```bash
cd ~/csd/Side-Projects/Voicewright
git switch feat/scripts-outputs
.venv/bin/voicewright
```

Keep the terminal visible. Wait for the blue startup bar to go away.

You need one saved Voice. If **Saved Voices** is empty, design one first (e.g. `A gravelly
older man with a slow, calm, warm voice.`), then Accept it as `Narrator`. The steps below
call it "your Voice".

## Part C — The Script flow

### C1 — Pick a Voice

Scroll to **Scripts**.

- [ ] The **Voice** list shows your saved Voice(s)
- [ ] The help line explains `[emotion]`, `{sound}`, and `(effect)`

**Notes:**

### C2 — Check a Script with every kind of problem

Paste this into **Script** exactly (two lines) and click **Check**:

```text
[furious] Get away from the door! {creaky-door} (gasp) {thunder}
[sad It's too late now.
```

(If you already have a `{creaky-door}` sound, use another name nobody has.)

- [ ] "Fix these before generating:" shows, with all of these at once:
  - [ ] `[furious]`: your Voice has no furious preset, with an **Add furious to …** button
  - [ ] `{creaky-door}` isn't in your Sound library, with a **Find it on Freesound** button
  - [ ] `{thunder}` is listed the same way, if it's not in your library
  - [ ] **Line 2, column 1**: the `[` is never closed
- [ ] A warning says `(gasp)` is skipped because Vocal effects can't be rendered yet
- [ ] Nothing started: no blue job bar

**Notes:**

### C3 — Jump to the error

Click **Line 2, column 1**.

- [ ] The cursor jumps into the Script, with the `[` on line 2 selected

**Notes:**

### C4 — Fill in a missing sound from the check

Click **Find it on Freesound** next to `{creaky-door}`.

- [ ] The page scrolls to **Find a sound on Freesound** and searches for `creaky door`
- [ ] Each result's name box says `creaky-door`

Preview a few, then click **Add** on one you like.

- [ ] `{creaky-door}` is added to **Your Sound library**
- [ ] Scroll back to **Scripts**: the check has updated by itself, and `{creaky-door}` is no
  longer listed

If `{thunder}` is still listed, add a thunder sound the same way.

**Notes:**

### C5 — Fill in a missing emotion from the check

Click **Add furious to …**.

- [ ] Your Voice's card opens at **Add an Emotion preset**, with `furious` typed in

Click **Design it**, wait for the take, listen, and click **Accept** on the yellow box.

- [ ] Back in **Scripts**, the check has updated by itself: only the Line 2 error is left

**Seconds for Design it:** ___

**Notes:**

### C6 — Fix the tag

Change `[sad It's` to `[sad] It's` and click **Check**.

- [ ] "Ready to generate: 4 Segments." (two lines and two sounds; `(gasp)` doesn't count)
- [ ] The `(gasp)` warning is still shown

**Notes:**

### C7 — Generate

Click **Generate**.

- [ ] The blue bar shows lines like `Speaking “Get away from the door!” (furious) (Segment 1 of 4)`
  and `Adding {creaky-door} (Segment 2 of 4)`, then "Putting the Output together"
- [ ] While it runs, **Generate**, **Design**, and the other job buttons are greyed out
  (story 49)
- [ ] When it's done, "Done: a N s Output" shows, the Output is at the top of **Recent
  Outputs**, and it starts playing by itself

**Seconds from click to done:** ___

**Notes:**

### C8 — A long passage (story 45)

Replace the Script with this (about 120 words, untagged) and click **Generate**:

```text
The road out of town runs past the old grain elevator and the river. Most mornings it's
quiet, just the wind and a few trucks heading for the highway. I've driven it so many times
I could do it with my eyes closed, though I wouldn't recommend it. In spring the fields on
either side turn a green so bright it almost hurts, and the ditches fill with water that
reflects the sky. By August everything is gold and dust, and the air smells like cut hay and
diesel. My father used to say you could tell the season with your eyes shut, just by the
sound the tires made. He was right about that, and about most things, though I didn't
admit it until much later.
```

- [ ] It finishes, and the Output plays every sentence through to "until much later." with
  nothing cut off or skipped

**Seconds from click to done:** ___  **Output length:** ___ s

**Notes:**

### C9 — Save an Output

On the C7 Output in **Recent Outputs**, click **Save**.

- [ ] Its **Save** button turns into "Saved"
- [ ] It appears under **Saved outputs**, with a Sounds line crediting `{creaky-door}` (and
  `{thunder}`): title, author, and license
- [ ] **Record (JSON)** opens the record in a new tab: the Script, the Voice, the exaggeration
  and cfg for `neutral`, `furious`, and `sad`, and the sounds with their source links
- [ ] In Finder, `~/Voicewright/saved/` holds a `.wav` and a `.json` with the same name,
  starting with the date and your Voice's name

**Notes:**

### C10 — Download

- [ ] **Download WAV** on a Recent Output saves a file named like `narrator-20261107-143022.wav`
- [ ] **Download WAV** on the Saved output saves its file
- [ ] Both open and play in another app (QuickTime or Music)

**Notes:**

### C11 — A rejected Script starts nothing

Change the Script to `[nope] Hello.` and click **Generate** (not Check).

- [ ] The problem list shows `[nope]` missing, with an **Add nope to …** button
- [ ] No job bar appeared, and no new Output was added

**Notes:**

### C12 — The cache size

Set **Keep the last** to `6`.

- [ ] `~/.config/voicewright/config.toml` now says `output_cache_size = 6`, and the rest of
  the file (your key, the data folder) is unchanged

**Notes:**

### C13 — Restart

Stop the app with **Ctrl+C** and start it again. Reload the page.

- [ ] **Recent Outputs** is empty ("No Outputs yet.")
- [ ] **Saved outputs** still has the C9 Output, and it plays
- [ ] The Script box still has `[nope] Hello.` and the same Voice is picked
- [ ] **Keep the last** still says `6`

**Notes:**

## Part D — Listening

Play the C7 Output (from **Saved outputs**) and answer by ear.

- [ ] The furious line sounds angry, and "It's too late now." sounds sad
- [ ] Both lines sound like the same person as your Voice's neutral clip
- [ ] The creaky door and thunder come where they're written: after the first line, before
  the second
- [ ] The sounds aren't much louder or quieter than the speech
- [ ] No clicks or pops where one piece meets the next

**The gaps between pieces are (too short / about right / too long):** ___

**Anything else about the sound:**

## Wrap-up

- [ ] No errors or tracebacks in the terminal (paste any below)
- [ ] The page never froze or got stuck with the job bar showing

**Terminal errors (paste):**

```text
```

**Anything confusing, slow, or annoying, even if it worked:**

**Does the Script flow pass? (yes / no / yes with issues):**
