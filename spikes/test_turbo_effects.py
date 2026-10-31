"""Spike: vocal effects with Chatterbox Turbo's inline tags, cloned from a designed neutral clip.

Usage: python test_turbo_effects.py voxcpm   (or: qwen)
Turbo's documented tags: [laugh] [chuckle] [sigh] [cough]. (scream) isn't listed; tried anyway.
"""
import os, sys
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import torch
import torchaudio as ta
from chatterbox.tts_turbo import ChatterboxTurboTTS
from common import Timer, report, out, need

source = sys.argv[1] if len(sys.argv) > 1 else "voxcpm"
ref = out(f"{source}_neutral.wav")
need(ref)
device = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"device: {device}")
with Timer("load model"):
    model = ChatterboxTurboTTS.from_pretrained(device=device)

LINES = {
    "laugh":   "Oh, that's the best thing I've heard all week. [laugh] You really did that?",
    "chuckle": "Well, [chuckle] I suppose that's one way to fix a fence.",
    "sigh":    "[sigh] I guess we'll have to start over in the morning.",
    "cough":   "Sorry, [cough] it's dusty out in that barn.",
    "scream":  "Get away from there! [scream]",
}
for tag, text in LINES.items():
    name = f"turbo_{source}_{tag}.wav"
    with Timer(name) as t:
        wav = model.generate(text, audio_prompt_path=ref)
    ta.save(out(name), wav, model.sr)
    report(name, t.s, wav.shape[-1] / model.sr)
print("Done. Listen to spikes/out/turbo_*.wav")
