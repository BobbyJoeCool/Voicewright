# Voicewright

Local text-to-speech studio: users build reusable voices, then turn tagged scripts into finished audio.

## Language

### Voices

**Voice**:
A saved, reusable speaker identity: one neutral reference clip plus its emotion presets.
_Avoid_: Speaker, character, model

**Draft voice**:
A Voice still under review, before the user accepts or discards it. Not usable by Scripts.
_Avoid_: Pending voice, temp voice

**Emotion preset**:
One emotion a Voice can deliver: its reference clip and its tuning values. A Voice starts with the Default emotion set and can gain, lose, or retune presets later.
_Avoid_: Emotion sample, emotion clip, emotion variant, delivery

**Default emotion set**:
The list of emotions every new Voice starts with.
_Avoid_: Starter emotions, base emotions

**Reference clip**:
The audio file a Voice or Emotion preset is cloned from. The neutral reference clip defines the Voice's identity.
_Avoid_: Sample, voice (for the file)

**Character**:
A named role in a script that is assigned a Voice. Not in v1; reserved so "Voice" never means a role.
_Avoid_: Speaker, persona

### Scripts

**Script**:
The tagged text a user submits to produce one audio file. In v1 a Script uses exactly one Voice.

**Segment**:
One ordered piece of a parsed Script: speech, a vocal effect, or a sound effect.
_Avoid_: Chunk, line, block

**Emotion tag**:
A `[square-bracket]` marker that sets the emotion for all following speech until the next Emotion tag.
_Avoid_: Mood, style tag

**Vocal effect**:
A non-verbal sound made in the Voice's own voice, written `(like this)`, such as a laugh or sigh.
_Avoid_: Vocalization, sound effect

**Sound effect**:
A sound not made by the Voice, written `{like this}`, such as an explosion.
_Avoid_: SFX, vocal effect, foley

**Sound library**:
The local collection of named sounds that Sound effects resolve to, each kept with its source and license.
_Avoid_: SFX folder, sound bank

### Outputs

**Output**:
The finished audio file produced from one Script. Temporary unless saved.
_Avoid_: Render, result, clip

**Saved output**:
An Output the user chose to keep, stored with a record of the Script, Voice, preset values, and sound credits that produced it.
_Avoid_: Export

## Relationships

- A **Voice** has one neutral **Reference clip** and many **Emotion presets**
- A **Draft voice** becomes a **Voice** when accepted
- A **Script** produces one **Output**; saving it makes a **Saved output**
- A **Script** parses into many ordered **Segments**
- In v1, a **Script** is rendered with one **Voice**; later, each **Character** in a Script is assigned a **Voice**
- A **Sound effect** name must match an entry in the **Sound library**, or the Script is rejected before generation
- An **Emotion tag** in a Script must match an emotion the chosen **Voice** has, or the Script is rejected before generation
