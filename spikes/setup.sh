#!/usr/bin/env bash
# Creates one virtual environment per model so their PyTorch/MLX versions can't conflict.
# Run from the spikes folder:  bash setup.sh
set -euo pipefail
PY="${PY:-python3.11}"
command -v "$PY" >/dev/null || { echo "$PY not found. Run: brew install python@3.11"; exit 1; }
command -v ffmpeg >/dev/null || echo "Note: ffmpeg not found (brew install ffmpeg). Not needed for these spikes, needed for the app."

make_env () {  # name, packages...
  local name="$1"; shift
  echo "== $name =="
  "$PY" -m venv ".venvs/$name"
  ".venvs/$name/bin/pip" install --upgrade pip -q
  ".venvs/$name/bin/pip" install "$@"
}
make_env voxcpm     voxcpm soundfile
make_env qwen       mlx-audio soundfile
make_env chatterbox chatterbox-mlx
make_env turbo      chatterbox-tts
echo "All environments created in spikes/.venvs/"
