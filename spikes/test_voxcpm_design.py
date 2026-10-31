"""Spike: VoxCPM2 voice design on the M2.

1. Design a neutral voice from DESCRIPTION.
2. Emotion presets two ways, for the consistency test:
   a) designed separately from the description + emotion  -> voxcpm_design_<emotion>.wav
   b) cloned from the neutral clip with a style note       -> voxcpm_clone_<emotion>.wav
"""
import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import soundfile as sf
import torch
from voxcpm import VoxCPM
from common import DESCRIPTION, NEUTRAL_TEXT, EMOTIONS, Timer, report, out

print(f"MPS available: {torch.backends.mps.is_available()}")
with Timer("load model"):
    model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
sr = model.tts_model.sample_rate


def gen(name, text, **kw):
    with Timer(name) as t:
        wav = model.generate(text=text, cfg_value=2.0, inference_timesteps=10, seed=42, **kw)
    sf.write(out(name), wav, sr)
    report(name, t.s, len(wav) / sr)


gen("voxcpm_neutral.wav", f"({DESCRIPTION}){NEUTRAL_TEXT}")
for emo, (line, _, _) in EMOTIONS.items():
    gen(f"voxcpm_design_{emo}.wav", f"({DESCRIPTION} Speaking in a {emo} tone.){line}")
    gen(f"voxcpm_clone_{emo}.wav", f"({emo} tone){line}",
        reference_wav_path=out("voxcpm_neutral.wav"))
print("Done. Listen to spikes/out/voxcpm_*.wav")
