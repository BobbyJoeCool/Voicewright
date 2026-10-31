# Qwen3-TTS designs every Emotion preset clip from the description

The design doc planned to design only the neutral clip from the description and clone each Emotion preset from it, so every emotion would be the same person. The step 0.2 spikes on the M2 changed that. Qwen3-TTS VoiceDesign produced a much better voice and much better emotions than VoxCPM2, ran in 5.8 GB with green memory pressure, and reached an RTF of 1.37. Cloning an emotion from the neutral clip kept the voice only "close": Chatterbox clones from either engine's neutral clip, and VoxCPM2 style-cloning from Qwen's neutral clip. The user judged that cloning itself was what made the voice drift, and chose to have Qwen design each Emotion preset clip from the Voice's description plus the emotion.

## Considered Options

- **Qwen design + VoxCPM2 style-cloning from the neutral clip:** tested, close to the same man and emotions came through, but adds a 13 GB model that pushed memory pressure to yellow, and the voice still drifted.
- **Qwen design + Chatterbox cloning with exaggeration and cfg:** tested, close to the same man; the user found VoxCPM2 cloning clearly better.
- **VoxCPM2 for both:** the same man, but a weaker voice and emotions that only "sort of" landed (sad sounded thoughtful, excited sounded upset).

## Consequences

- Not verified in the spike: whether Qwen's separately designed emotions sound like the same man as its neutral clip. The Draft voice review (regenerate one preset until it matches) is the safeguard. If drift is a problem in practice, revisit with Qwen design + VoxCPM2 cloning.
- The description, not the neutral clip, is what every preset is designed from. A saved Voice keeps its description and it can't be edited, so a custom preset added later is designed from the same words.
- Voice creation needs only Qwen3-TTS; VoxCPM2 is not used in v1. Script generation still runs on Chatterbox, cloning from each preset's clip with its exaggeration and cfg (ADR 0002).
