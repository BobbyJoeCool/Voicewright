"""Shared steps for the Script and Output tests: a saved Voice and some sounds to use."""

import array
import io
import itertools
import math
import wave

from voices import designed_draft, run_job, succeeded


def saved_voice(client, name: str = "Old Narrator") -> dict:
    """A saved Voice with the Default emotion set: neutral, angry, sad, excited."""
    response = client.post("/voices", json={"draft_id": designed_draft(client)["id"], "name": name})
    assert response.status_code == 201, response.text
    return response.json()


def add_sound(client, name: str, freesound_id: int = 101) -> dict:
    response = client.post("/sounds", json={"freesound_id": freesound_id, "name": name})
    assert response.status_code == 201, response.text
    return response.json()


def check(client, voice: dict, script: str):
    return client.post("/scripts/check", json={"voice_id": voice["id"], "script": script})


def generate(client, voice: dict, script: str) -> dict:
    """Generate a Script and wait for the job; return the job's final status."""
    return run_job(client, "/scripts/generate", {"voice_id": voice["id"], "script": script})


def generated_output(client, voice: dict, script: str) -> dict:
    """Generate a Script and return the Output it made."""
    result = succeeded(generate(client, voice, script))
    response = client.get(f"/outputs/{result['output_id']}")
    assert response.status_code == 200, response.text
    return response.json()


def read_wav(data: bytes) -> tuple[list[int], int, int, int]:
    """(samples, rate, channels, sample width) of a WAV."""
    with wave.open(io.BytesIO(data)) as wav:
        frames = wav.readframes(wav.getnframes())
        shape = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
    return list(array.array("h", frames)), *shape


def pieces(data: bytes, quiet: int = 2, gap_seconds: float = 0.05) -> list[list[int]]:
    """The pieces of an Output: the runs of sound between silences of at least `gap_seconds`."""
    samples, rate, _, _ = read_wav(data)
    gap = int(rate * gap_seconds)
    found, current, silent = [], [], 0
    for sample in samples:
        if abs(sample) <= quiet:
            silent += 1
            if silent >= gap and current:
                found.append(current[: len(current) - silent + 1])
                current = []
            if current:
                current.append(sample)
        else:
            silent = 0
            current.append(sample)
    if current:
        found.append(current)
    return found


def pitch(samples: list[int], rate: int) -> float:
    """A tone's pitch in Hz, from how often it crosses zero."""
    crossings = sum(1 for a, b in itertools.pairwise(samples) if (a < 0) != (b < 0))
    return crossings / 2 / (len(samples) / rate)


def loudness(samples: list[int]) -> float:
    """RMS level in dB below full scale."""
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return 20 * math.log10(rms / 32768)
