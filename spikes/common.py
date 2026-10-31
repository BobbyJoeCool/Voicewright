"""Shared helpers for the model spikes: timing, peak memory, output paths."""
import os, resource, sys, time
from pathlib import Path

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

DESCRIPTION = "A gravelly older man with a slow, calm, warm voice."
NEUTRAL_TEXT = (
    "The road out of town runs past the old grain elevator and the river. "
    "Most mornings it's quiet, just the wind and a few trucks heading for the highway. "
    "I've driven it so many times I could do it with my eyes closed."
)
EMOTIONS = {
    # emotion: (sample line, chatterbox exaggeration, chatterbox cfg) — starting values from docs/design.md
    "angry":   ("I told you to stay out of my workshop, and you did it anyway!", 0.7, 0.3),
    "sad":     ("I kept his letters. I just never had the heart to read them again.", 0.3, 0.5),
    "excited": ("We did it! The whole crop came in, every last row of it!", 0.65, 0.35),
}


def peak_rss_gb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e9 if sys.platform == "darwin" else r / 1e6  # bytes on macOS, KB on Linux


def mlx_peak_gb():
    try:
        import mlx.core as mx
        f = getattr(mx, "get_peak_memory", None) or mx.metal.get_peak_memory
        return f() / 1e9
    except Exception:
        return None


class Timer:
    def __init__(self, label): self.label = label
    def __enter__(self): self.t = time.perf_counter(); return self
    def __exit__(self, *a):
        self.s = time.perf_counter() - self.t
        print(f"  {self.label}: {self.s:.1f}s")


def report(name: str, seconds: float, audio_seconds: float):
    rtf = seconds / audio_seconds if audio_seconds else float("nan")
    mlx = mlx_peak_gb()
    extra = f", MLX peak {mlx:.1f} GB" if mlx else ""
    print(f"  -> {name}: {audio_seconds:.1f}s audio in {seconds:.1f}s (RTF {rtf:.2f}), "
          f"peak RSS {peak_rss_gb():.1f} GB{extra}")


def out(name: str) -> str:
    return str(OUT / name)


def need(path: str):
    if not os.path.exists(path):
        sys.exit(f"Missing {path}. Run the voice-design test first (see spikes/README.md).")
