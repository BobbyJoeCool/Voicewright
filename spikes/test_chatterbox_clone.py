"""Spike: Chatterbox (chatterbox-mlx, hybrid-mlx) emotion presets cloned from a designed neutral clip.

Usage: python test_chatterbox_clone.py voxcpm   (or: qwen)
Writes chatterbox_from_<source>_<emotion>.wav using the starting exaggeration/cfg values.
"""
import sys
import torchaudio as ta
from chatterbox.tts_mlx import ChatterboxTTSMLX
from common import EMOTIONS, Timer, report, out, need

source = sys.argv[1] if len(sys.argv) > 1 else "voxcpm"
ref = out(f"{source}_neutral.wav")
need(ref)
with Timer("load model"):
    model = ChatterboxTTSMLX.from_pretrained(device="hybrid-mlx")

for emo, (line, exaggeration, cfg) in EMOTIONS.items():
    name = f"chatterbox_from_{source}_{emo}.wav"
    with Timer(name) as t:
        wav = model.generate(line, audio_prompt_path=ref, exaggeration=exaggeration, cfg_weight=cfg)
    ta.save(out(name), wav, model.sr)
    report(name, t.s, wav.shape[-1] / model.sr)
print(f"Done. Compare spikes/out/chatterbox_from_{source}_*.wav with {source}_design_*.wav")
