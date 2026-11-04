"""Standard WAV: the one audio format the app keeps and assembles (GLOSSARY: Standard WAV)."""

import io
import wave


def standard_wav(samples, rate: int) -> bytes:
    """Float samples from -1 to 1 (a numpy array) as standard WAV bytes: 16-bit PCM, mono."""
    import numpy as np  # comes with the model extras; only real engines produce float samples

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()
