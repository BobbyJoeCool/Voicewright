"""The Audio converter: turns any supported audio or video file into the app's standard WAV."""

import shutil
from pathlib import Path

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

SUPPORTED = "MP3, M4A, FLAC, OGG, AAC, WAV, or a video with sound"


class UnsupportedAudio(Exception):
    """The file has no audio that ffmpeg can read."""


class FfmpegMissing(Exception):
    """ffmpeg or ffprobe isn't installed, so nothing can be converted."""


def convert(source: Path, destination: Path) -> None:
    """Write the audio in `source` to `destination` as standard WAV: 16-bit PCM, mono.

    The sample rate is kept as it is. Raises UnsupportedAudio or FfmpegMissing.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None or shutil.which("ffprobe") is None:
        raise FfmpegMissing
    # pydub looks ffmpeg up once, when it is imported; use the one on the PATH now.
    AudioSegment.converter = ffmpeg
    try:
        audio = AudioSegment.from_file(source)
    except CouldntDecodeError:
        raise UnsupportedAudio from None
    except IndexError:
        # pydub's way of saying the file has streams but none of them is audio (a silent video).
        raise UnsupportedAudio from None
    audio.set_channels(1).set_sample_width(2).export(destination, format="wav")
