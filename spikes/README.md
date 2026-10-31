# Model spikes

Throwaway tests that answer the open questions in `docs/design.md` before v1 is built. Each model gets its own virtual environment in `.venvs/` so their PyTorch and MLX versions can't conflict. Generated audio goes to `out/`. Both folders are gitignored.

| Script | Answers |
|---|---|
| `test_voxcpm_design.py` | Does VoxCPM2 design voices acceptably on the M2? Also produces design-vs-clone emotion samples |
| `test_qwen_design.py` | Does Qwen3-TTS VoiceDesign run acceptably on the M2? |
| `test_chatterbox_clone.py` | Do Chatterbox emotion presets cloned from a designed neutral clip still sound like the same person? |
| `test_turbo_effects.py` | Can Chatterbox Turbo produce laughs, sighs, and similar in a cloned voice? |

## Install

1. `brew install python@3.11 ffmpeg`
2. `cd spikes && bash setup.sh` (creates four environments; a few minutes)

Each model downloads its weights from Hugging Face on first run, several GB each.

## Run

Run one model at a time and watch Memory Pressure in Activity Monitor while it runs. Close other heavy apps first.

1. `.venvs/voxcpm/bin/python test_voxcpm_design.py`
2. `.venvs/qwen/bin/python test_qwen_design.py`
3. `.venvs/chatterbox/bin/python test_chatterbox_clone.py voxcpm` (and/or `qwen`)
4. `.venvs/turbo/bin/python test_turbo_effects.py voxcpm` (and/or `qwen`)

Each line printed looks like `-> voxcpm_neutral.wav: 14.2s audio in 31.0s (RTF 2.18), peak RSS 9.8 GB`. RTF is seconds of work per second of audio; lower is faster.

## What to judge

- **Voice design passes** if the neutral clip matches the description, sounds clean enough to clone from, runs without memory pressure going red, and an RTF up to about 3 feels tolerable to you.
- **Consistency:** compare `*_design_<emotion>.wav` (designed separately) with `voxcpm_clone_<emotion>.wav` and `chatterbox_from_*_<emotion>.wav` (cloned from neutral). The approach in the design doc wins if the cloned ones sound more like the same man.
- **Vocal effects pass** if the laugh or sigh sounds natural and in the same voice, not read out as a word.
