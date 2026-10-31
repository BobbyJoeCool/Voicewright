"""Spike: VoxCPM2 style-cloned emotion presets from another engine's neutral clip.

Usage: python test_voxcpm_clone_from.py qwen   (or: voxcpm)
Writes voxcpm_clone_from_<source>_<emotion>.wav. Answers whether Qwen3-TTS design
plus VoxCPM2 cloning stays the same person.
"""
import os, sys
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import soundfile as sf
import torch
from voxcpm import VoxCPM
from common import EMOTIONS, Timer, report, out, need

source = sys.argv[1] if len(sys.argv) > 1 else "qwen"
ref = out(f"{source}_neutral.wav")
need(ref)
with Timer("load model"):
    model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
sr = model.tts_model.sample_rate

for emo, (line, _, _) in EMOTIONS.items():
    name = f"voxcpm_clone_from_{source}_{emo}.wav"
    torch.manual_seed(42)  # voxcpm 2.0.3's generate() takes no seed argument
    with Timer(name) as t:
        wav = model.generate(text=f"({emo} tone){line}", cfg_value=2.0, inference_timesteps=10,
                             reference_wav_path=ref)
    sf.write(out(name), wav, sr)
    report(name, t.s, len(wav) / sr)
print(f"Done. Compare spikes/out/voxcpm_clone_from_{source}_*.wav with {source}_neutral.wav")
