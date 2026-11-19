"""The model manager on its own: one large model at a time, and what happens when one won't load.

The route-level behavior is in test_jobs.py; these cover the manager's own edge cases directly.
"""

import pytest
from fakes import FakeEngines, load_error

from voicewright.engines import Engines, ModelLoadError, NoVocalEffects, OutOfMemory
from voicewright.model_manager import SPEECH, VOICE_DESIGN, ModelManager


@pytest.fixture
def fakes():
    return FakeEngines()


@pytest.fixture
def models(fakes):
    return ModelManager(fakes.engines())


def test_nothing_is_loaded_until_a_model_is_used(models, fakes):
    assert models.loaded is None
    assert fakes.events == []


def test_using_a_model_loads_it_and_it_stays_loaded(models, fakes):
    with models.speech() as engine:
        assert models.loaded == SPEECH
        engine.speak("Hello.", "missing.wav", 0.5, 0.5)

    assert models.loaded == SPEECH
    assert fakes.events == ["load speech"]


def test_switching_models_closes_the_first_before_loading_the_second(models, fakes):
    with models.voice_design():
        pass
    with models.speech():
        assert models.loaded == SPEECH

    # Voice design was loaded before, so it comes back once speech is done.
    assert fakes.events == [
        "load voice design",
        "close voice design",
        "load speech",
        "close speech",
        "load voice design",
    ]
    assert fakes.most_loaded_at_once == 1


def test_preloading_speech_twice_loads_it_once(models, fakes):
    models.preload_speech()
    models.preload_speech()

    assert fakes.events == ["load speech"]


def test_a_model_that_is_not_installed_raises_a_readable_load_error(models, fakes):
    fakes.fail_to_load["speech"] = load_error("speech model", "the weights aren't downloaded")

    with pytest.raises(ModelLoadError, match="couldn't load the speech model: the weights"):
        with models.speech():
            pass

    assert models.loaded is None


def test_a_loader_failing_its_own_way_becomes_a_load_error_naming_the_model(fakes):
    def broken():
        raise FileNotFoundError("no such file: model.safetensors")

    models = ModelManager(Engines(broken, broken, NoVocalEffects()))

    with pytest.raises(ModelLoadError, match="speech model: no such file"):
        models.preload_speech()


def test_a_loader_error_with_no_message_is_named_by_its_type():
    def broken():
        raise KeyError()

    models = ModelManager(Engines(broken, broken, NoVocalEffects()))

    with pytest.raises(ModelLoadError, match="voice design model: KeyError"):
        with models.voice_design():
            pass


def test_memory_error_while_loading_becomes_out_of_memory_naming_the_model():
    def too_big():
        raise MemoryError

    models = ModelManager(Engines(too_big, too_big, NoVocalEffects()))

    with pytest.raises(OutOfMemory, match=f"loading the {SPEECH}"):
        models.preload_speech()
    assert models.loaded is None


def test_when_the_borrowed_model_is_done_the_previous_one_comes_back(models, fakes):
    models.preload_speech()

    with models.voice_design():
        assert models.loaded == VOICE_DESIGN

    assert models.loaded == SPEECH
    assert fakes.events[-1] == "load speech"


def test_if_the_previous_model_cannot_come_back_the_work_still_succeeds(models, fakes, caplog):
    models.preload_speech()
    # Speech loads once, then fails when it is brought back after voice design.
    fakes.fail_to_load["speech"] = OutOfMemory("no room")

    with models.voice_design() as engine:
        engine.design("A calm voice.", "Hello.")

    assert models.loaded is None, "nothing stays loaded; the next use loads speech again"
    assert "couldn't reload the speech model" in caplog.text

    del fakes.fail_to_load["speech"]
    with models.speech():
        pass
    assert models.loaded == SPEECH


def test_a_model_whose_close_fails_is_still_dropped_and_never_doubled_up(fakes):
    class Fragile:
        def __init__(self):
            fakes.events.append("load fragile")

        def close(self):
            fakes.events.append("close fragile")
            raise RuntimeError("close failed")

    loaders = fakes.engines()
    models = ModelManager(Engines(Fragile, loaders.load_voice_design, NoVocalEffects()))
    models.preload_speech()

    with pytest.raises(RuntimeError, match="close failed"):
        with models.voice_design():
            pass

    # The failed close dropped the speech model, so voice design never loaded beside it, and
    # the speech model was loaded fresh afterwards.
    assert fakes.events == ["load fragile", "close fragile", "load fragile"]
    assert models.loaded == SPEECH
