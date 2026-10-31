"""Spike: Qwen3-TTS VoiceDesign (via mlx-audio) on the M2.

1. Design a neutral voice from DESCRIPTION.
2. Design each emotion separately (consistency test, option a).
   Option b (clone from neutral) is done by test_chatterbox_clone.py, because
   Qwen's Base clone model takes no emotion instruction.
"""
import numpy as np
import soundfile as sf
import mlx.core as mx
from mlx_audio.tts.utils import load_model
from common import DESCRIPTION, NEUTRAL_TEXT, EMOTIONS, Timer, report, out

MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"
with Timer("load model"):
    model = load_model(MODEL)
sr = model.sample_rate


def gen(name, text, instruct):
    with Timer(name) as t:
        results = list(model.generate_voice_design(text=text, language="English", instruct=instruct))
        audio = np.array(mx.concatenate([r.audio for r in results], axis=0))
    sf.write(out(name), audio, sr)
    report(name, t.s, len(audio) / sr)


gen("qwen_neutral.wav", NEUTRAL_TEXT, DESCRIPTION)
for emo, (line, _, _) in EMOTIONS.items():
    gen(f"qwen_design_{emo}.wav", line, f"{DESCRIPTION} Speaking in a {emo} tone.")
print("Done. Listen to spikes/out/qwen_*.wav")
