# Emotion presets store Chatterbox-specific tuning values

Each emotion preset stores a reference clip plus Chatterbox's `exaggeration` and `cfg` values, tuned by ear. We chose Chatterbox (`chatterbox-mlx`, `hybrid-mlx` backend) because it is the only speech and cloning model tested and working on the M2. Exposing its own settings gives the most direct control over delivery. A model-neutral scale (for example "intensity 1 to 10") would need a translation layer we can't calibrate until a second model exists.

## Consequences

- Switching speech models means retuning every emotion preset on every saved Voice. The reference clips carry over; the numbers don't.
- Saved output records store these values, so they describe how the output was made with Chatterbox specifically.
- If a second speech model is added, revisit this: either store values per model, or add a neutral scale and map it to each model.
