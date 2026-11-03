"""The model manager: keeps at most one large model in memory at a time."""

import contextlib
import gc
import logging
import threading
from collections.abc import Callable, Iterator

from voicewright.engines import (
    Engines,
    LargeModel,
    ModelLoadError,
    OutOfMemory,
    SpeechEngine,
    VoiceDesignEngine,
)

log = logging.getLogger(__name__)

SPEECH = "speech model"
VOICE_DESIGN = "voice design model"


class ModelManager:
    """Hands out the large models, one at a time.

    Using a model that isn't loaded closes the one that is, then loads it. When that use ends,
    the model that was loaded before comes back, so the speech model, once loaded, stays
    ready for Scripts while voice design borrows the memory.
    """

    def __init__(self, engines: Engines):
        self._loaders: dict[str, Callable[[], LargeModel]] = {
            SPEECH: engines.load_speech,
            VOICE_DESIGN: engines.load_voice_design,
        }
        self._lock = threading.RLock()
        self._loaded_name: str | None = None
        self._loaded: LargeModel | None = None

    @property
    def loaded(self) -> str | None:
        """The name of the model in memory, if any."""
        return self._loaded_name

    def speech(self) -> contextlib.AbstractContextManager[SpeechEngine]:
        return self._use(SPEECH)

    def voice_design(self) -> contextlib.AbstractContextManager[VoiceDesignEngine]:
        return self._use(VOICE_DESIGN)

    def preload_speech(self) -> None:
        """Load the speech model now, so the first Script doesn't wait for it."""
        with self._lock:
            self._switch_to(SPEECH)

    @contextlib.contextmanager
    def _use(self, name: str) -> Iterator:
        with self._lock:
            previous = self._loaded_name
            try:
                # Inside the try: if this model fails to load, the previous one still comes back.
                self._switch_to(name)
                yield self._loaded
            finally:
                if previous is not None and previous != name:
                    self._restore(previous)

    def _restore(self, name: str) -> None:
        try:
            self._switch_to(name)
        except (ModelLoadError, OutOfMemory):
            # The work this model was borrowed for is done; don't fail it. Nothing stays
            # loaded, and the next use loads the model again and reports its own error.
            log.warning("couldn't reload the %s; it loads again when next needed", name)

    def _switch_to(self, name: str) -> None:
        if self._loaded_name == name:
            return
        self._unload()
        try:
            self._loaded = self._loaders[name]()
        except (ModelLoadError, OutOfMemory):
            raise
        except MemoryError:
            raise OutOfMemory(f"ran out of memory loading the {name}") from None
        except Exception as error:
            # A real loader fails in its library's own way (missing weights, bad cache).
            raise ModelLoadError(name, str(error) or type(error).__name__) from error
        self._loaded_name = name

    def _unload(self) -> None:
        if self._loaded is None:
            return
        model, self._loaded, self._loaded_name = self._loaded, None, None
        try:
            model.close()
        finally:
            del model
            # Drop every reference now, so the memory is free before the next model loads.
            gc.collect()
