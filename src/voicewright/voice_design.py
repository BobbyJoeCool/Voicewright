"""Designing a Draft voice: a job that designs the neutral clip and every default Emotion preset.

Each clip is designed by the voice design engine from the Voice's description (plus the
emotion, for presets; ADR 0003), reading that emotion's sample sentence from the Default
emotion set. Each clip is saved as soon as it is designed, so a crash keeps the ones done.
"""

from collections.abc import Sequence

from voicewright.default_emotions import DefaultEmotion
from voicewright.drafts import DraftStore
from voicewright.model_manager import ModelManager

NEUTRAL = "neutral"


def neutral_first(emotions: Sequence[DefaultEmotion]) -> list[DefaultEmotion]:
    """Neutral is designed first: it is the Voice's identity, the clip to judge the rest by."""
    return sorted(emotions, key=lambda emotion: emotion.name != NEUTRAL)


def design_draft_voice(
    drafts: DraftStore,
    models: ModelManager,
    emotions: Sequence[DefaultEmotion],
    description: str,
):
    """The job's work: returns {"draft_id": …} once every preset is designed."""
    order = neutral_first(emotions)

    def work(report):
        report(0, len(order), "Loading the voice design model")
        borrowed_from = models.loaded
        with models.voice_design() as engine:
            # Created only once the model has loaded: a failed load leaves no empty draft.
            draft = drafts.create(description, [emotion.name for emotion in order])
            for done, emotion in enumerate(order):
                what = (
                    "the neutral clip" if emotion.name == NEUTRAL else f"the {emotion.name} preset"
                )
                report(done, len(order), f"Designing {what}")
                wav = engine.design(
                    description,
                    emotion.sample,
                    emotion=None if emotion.name == NEUTRAL else emotion.name,
                )
                draft = drafts.save_preset(
                    draft, emotion.name, wav, emotion.exaggeration, emotion.cfg
                )
            # Leaving the block brings back the model that was loaded before, if any (speech).
            finishing = f"Reloading the {borrowed_from}" if borrowed_from else "Finishing"
            report(len(order), len(order), finishing)
        return {"draft_id": draft.id}

    return work
