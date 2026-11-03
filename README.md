# Voicewright
 An app using open source and free AI models that pipelines created AI voices and sound effects, and Turing text to speech using those crafted voices.

## Run it

Needs macOS with Python 3.11 or 3.12 (3.13 and newer won't work with the speech model).

1. `brew install python@3.11`
2. `python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'`
3. `.venv/bin/voicewright`

The last step starts the app at <http://127.0.0.1:8765/> and opens it in your browser. Running it again while it's up just opens the page, unless `--config` names a config file other than the default one. Use `--port` to pick another port.

### Settings and data

On first run the app writes a config file to `~/.config/voicewright/config.toml` (or wherever `--config` points) and creates the app data folder it names, `~/Voicewright` by default, with `voices`, `drafts`, `sounds`, `cache`, and `saved` subfolders. To move the data folder, set `data_folder` to a full path or one starting with `~`. The config file also holds the Output cache size (5 to 10) and your Freesound API key, so it is created readable only by you. Keep it out of git.

## Develop

Before each commit, run the checks:

```sh
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
```

Tests run the app in-process against a fresh temporary data folder, so they never touch your real config or data.
