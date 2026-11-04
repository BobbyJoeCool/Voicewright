"""Editing a saved Voice: the jobs that make its pending takes.

New and regenerated presets are designed from the Voice's locked description (plus the
emotion; ADR 0003). A retune is heard by speaking the preset's sample from its current clip at
the new values (ADR 0002). Each result waits as a pending take until it is accepted or rejected.
"""

from voicewright.drafts import DESIGN, PREVIEW
from voicewright.model_manager import ModelManager
from voicewright.voice_design import clip_name
from voicewright.voice_library import VoiceLibrary

# The sample sentence a custom preset reads when the user gives none: a line that can carry any
# emotion, so it doesn't fight the one being designed.
GENERIC_SAMPLE = (
    "I never thought it would come to this, but here we are, and there's no going back now."
)


def design_pending_take(
    library: VoiceLibrary,
    models: ModelManager,
    voice_id: str,
    emotion: str,
    sample: str,
    exaggeration: float,
    cfg: float,
):
    """Job: design a clip for a new or regenerated preset → {"take"} (pending)."""

    def work(report):
        borrowed_from = models.loaded
        report(0, 1, f"Designing {clip_name(emotion)}")
        description = library.get(voice_id).description
        with models.voice_design() as engine:
            wav = engine.design(description, sample, emotion=emotion)
            take = library.add_pending(voice_id, emotion, DESIGN, wav, exaggeration, cfg, sample)
            report(1, 1, f"Reloading the {borrowed_from}" if borrowed_from else "Finishing")
        return {"voice_id": voice_id, "take": take.id}

    return work


def retune_saved_preset(
    library: VoiceLibrary,
    models: ModelManager,
    voice_id: str,
    emotion: str,
    exaggeration: float,
    cfg: float,
):
    """Job: hear a saved preset at new values → {"take"} (pending; accepting keeps the values)."""

    def work(report):
        report(0, 1, f"Speaking {clip_name(emotion)} with the new values")
        preset = library.get(voice_id).presets[emotion]
        with models.speech() as speech:
            wav = speech.speak(
                preset.sample, library.clip_path(voice_id, emotion), exaggeration, cfg
            )
        take = library.add_pending(
            voice_id, emotion, PREVIEW, wav, exaggeration, cfg, preset.sample
        )
        return {"voice_id": voice_id, "take": take.id}

    return work
