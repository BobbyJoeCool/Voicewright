"""Designing and reviewing a Draft voice: the jobs that make its takes.

Each Reference clip is designed by the voice design engine from the Voice's description (plus
the emotion, for presets; ADR 0003), reading that emotion's sample sentence. A retune is heard
through the speech engine: the preset's sample sentence spoken from its current clip with the
new values, since those are Chatterbox settings (ADR 0002). Every result is saved as a take as
soon as it is made, so a crash keeps the ones done.
"""

from collections.abc import Sequence

from voicewright.default_emotions import DefaultEmotion
from voicewright.drafts import DraftStore, Emotion
from voicewright.model_manager import ModelManager

NEUTRAL = "neutral"


def neutral_first(emotions: Sequence[DefaultEmotion]) -> list[DefaultEmotion]:
    """Neutral is designed first: it is the Voice's identity, the clip to judge the rest by."""
    return sorted(emotions, key=lambda emotion: emotion.name != NEUTRAL)


def clip_name(emotion: str) -> str:
    return "the neutral clip" if emotion == NEUTRAL else f"the {emotion} preset"


def design_clips(drafts, models, draft_id, description, names, report, borrowed_from):
    """Design a new take for each named emotion, in order, reporting step i of len(names).

    `borrowed_from` is the model loaded before the job borrowed the memory: it comes back after.
    """
    with models.voice_design() as engine:
        for done, name in enumerate(names):
            report(done, len(names), f"Designing {clip_name(name)}")
            emotion = drafts.get(draft_id).emotion(name)
            wav = engine.design(
                description, emotion.sample, emotion=None if name == NEUTRAL else name
            )
            drafts.add_design_take(draft_id, name, wav, description)
        finishing = f"Reloading the {borrowed_from}" if borrowed_from else "Finishing"
        report(len(names), len(names), finishing)


def design_draft_voice(
    drafts: DraftStore,
    models: ModelManager,
    emotions: Sequence[DefaultEmotion],
    description: str,
):
    """Job: a new Draft voice with the neutral clip and every default preset → {"draft_id"}."""
    order = [Emotion(e.name, e.sample, e.exaggeration, e.cfg) for e in neutral_first(emotions)]

    def work(report):
        report(0, len(order), "Loading the voice design model")
        borrowed_from = models.loaded
        with models.voice_design():
            # Created only once the model has loaded: a failed load leaves no empty draft.
            draft = drafts.create(description, order)
            names = [e.name for e in order]
            design_clips(drafts, models, draft.id, description, names, report, borrowed_from)
        return {"draft_id": draft.id}

    return work


def regenerate_preset(drafts: DraftStore, models: ModelManager, draft_id: str, emotion: str):
    """Job: a new take of one preset (or the neutral clip), leaving the others alone."""

    def work(report):
        description = drafts.get(draft_id).description
        design_clips(drafts, models, draft_id, description, [emotion], report, models.loaded)
        return {"draft_id": draft_id, "take": drafts.get(draft_id).presets[emotion].take}

    return work


def redesign_draft_voice(drafts: DraftStore, models: ModelManager, draft_id: str, description: str):
    """Job: a new description, then a new take of every preset designed from it."""

    def work(report):
        draft = drafts.set_description(draft_id, description)
        names = [e.name for e in draft.emotions]
        design_clips(drafts, models, draft_id, description, names, report, models.loaded)
        return {"draft_id": draft_id}

    return work


def retune_preset(
    drafts: DraftStore,
    models: ModelManager,
    draft_id: str,
    emotion: str,
    exaggeration: float,
    cfg: float,
):
    """Job: hear a preset at new values; they become the preset's values → {"take"}."""

    def work(report):
        report(0, 1, f"Speaking {clip_name(emotion)} with the new values")
        draft = drafts.get(draft_id)
        clip = draft.presets[emotion].take
        with models.speech() as speech:
            wav = speech.speak(
                draft.emotion(emotion).sample, drafts.clip_path(draft, emotion), exaggeration, cfg
            )
        draft = drafts.add_preview_take(draft_id, emotion, wav, clip, exaggeration, cfg)
        return {"draft_id": draft_id, "take": draft.takes[-1].id}

    return work
