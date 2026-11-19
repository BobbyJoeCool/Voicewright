// The Scripts area: pick a Voice, write a Script, check it, generate it, then play, save, and
// download Outputs. It talks only to the HTTP API, through common.js.
(() => {
  "use strict";

  const { api, el, player, runJob } = window.Voicewright;
  const $ = (id) => document.getElementById(id);

  // The last check shown, to recheck it when a missing emotion or sound gets added.
  let lastCheck = null;
  // The Script and Voice being written survive a reload of the page.
  const SAVED_SCRIPT = "voicewright.script";
  const SAVED_VOICE = "voicewright.script-voice";
  // Storage can be refused (a private window); the page works without it.
  const recall = (key) => {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  };
  const remember = (key, value) => {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Not kept for next time; nothing else depends on it.
    }
  };
  // The saved Voices and library sounds, for the tag palette under the Script box.
  let voices = [];
  let sounds = [];

  // --- Small pieces -------------------------------------------------------------------------

  const seconds = (value) => `${Number(value).toFixed(1)} s`;
  const when = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  const excerpt = (text, length = 140) => {
    const flat = text.replace(/\s+/g, " ").trim();
    return flat.length > length ? `${flat.slice(0, length)}…` : flat;
  };
  const where = (problem) => `Line ${problem.line}, column ${problem.column}`;

  function showError(message) {
    $("script-error").textContent = message;
    $("script-error").hidden = !message;
  }

  // Select the character a problem points at, so it's easy to find in a long Script.
  function goTo(problem) {
    const text = $("script-text");
    text.focus();
    text.setSelectionRange(problem.position, problem.position + 1);
  }

  const request = () => ({ voice_id: $("script-voice").value, script: $("script-text").value });
  const voiceName = () => $("script-voice").selectedOptions[0]?.textContent ?? "the Voice";

  // --- Voices to pick from ------------------------------------------------------------------

  function showVoices(list) {
    voices = list;
    const select = $("script-voice");
    const chosen = select.value || recall(SAVED_VOICE);
    select.replaceChildren(...voices.map((v) => el("option", { value: v.id, text: v.name })));
    if (voices.some((v) => v.id === chosen)) select.value = chosen;
    $("script-no-voices").hidden = voices.length > 0;
    select.hidden = voices.length === 0;
    showPalette();
  }

  // --- The Script box -----------------------------------------------------------------------

  // The Script box is a textarea over a colored copy of its text. The coloring follows the
  // parser's rules (script.py): a tag opens with [ ( or {, closes on the same line before any
  // other bracket, and holds one name. A tag the parser would refuse gets a wavy underline.
  const MARKERS = { "[": ["]", "tok-emotion", /^[a-z][a-z0-9_-]*$/], "(": [")", "tok-effect", /^[a-z][a-z0-9_-]*$/], "{": ["}", "tok-sound", /^[a-z0-9][a-z0-9_-]{0,59}$/] };
  const CLOSERS = new Set(["]", ")", "}"]);
  const MAX_LENGTH = Number($("script-text").getAttribute("maxlength"));

  function closeOf(script, start, close) {
    for (let j = start + 1; j < script.length; j++) {
      const char = script[j];
      if (char === close) return j;
      if (char === "\n" || char in MARKERS || CLOSERS.has(char)) return -1;
    }
    return -1;
  }

  // The Script as text nodes and colored spans: never HTML, so typed markup stays as typed.
  function highlighted(script) {
    const nodes = [];
    let plain = 0;
    const flush = (end) => {
      if (end > plain) nodes.push(document.createTextNode(script.slice(plain, end)));
    };
    const mark = (start, end, className) => {
      flush(start);
      nodes.push(el("span", { class: className, text: script.slice(start, end) }));
      plain = end;
    };
    for (let i = 0; i < script.length; i++) {
      const char = script[i];
      if (CLOSERS.has(char)) {
        mark(i, i + 1, "tok-unknown");
      } else if (char in MARKERS) {
        const [close, className, pattern] = MARKERS[char];
        const end = closeOf(script, i, close);
        if (end === -1) {
          mark(i, i + 1, "tok-unknown");
        } else {
          const name = script.slice(i + 1, end).trim().toLowerCase();
          mark(i, end + 1, pattern.test(name) ? className : `${className} tok-unknown`);
          i = end;
        }
      }
    }
    flush(script.length);
    // A trailing newline needs something after it, or the copy ends a line short of the box.
    nodes.push(document.createTextNode("\u200b"));
    return nodes;
  }

  function showEditor() {
    const text = $("script-text");
    $("script-highlight").replaceChildren(...highlighted(text.value));
    // The box grows with the Script instead of scrolling inside itself.
    text.style.height = "auto";
    if (text.scrollHeight) text.style.height = `${text.scrollHeight}px`;
    const count = text.value.length;
    $("script-count").textContent = `${count.toLocaleString()} / ${MAX_LENGTH.toLocaleString()} characters`;
  }

  // Put `tag` in the Script at the cursor, with a space before it where words would touch.
  function insertTag(tag) {
    const text = $("script-text");
    const { selectionStart: start, selectionEnd: end, value } = text;
    const before = start > 0 && !/\s/.test(value[start - 1]) ? " " : "";
    const after = end < value.length && !/\s/.test(value[end]) ? " " : "";
    text.focus();
    text.setRangeText(`${before}${tag}${after}`, start, end, "end");
    text.dispatchEvent(new Event("input"));
  }

  // One-click tags: the chosen Voice's emotions and the library's sounds.
  function showPalette() {
    const voice = voices.find((v) => v.id === $("script-voice").value);
    const emotions = voice ? Object.keys(voice.presets) : [];
    const row = (label, chips) =>
      chips.length ? el("div", { class: "chips" }, el("span", { class: "palette-label", text: label }), ...chips) : null;
    const chip = (kind, tag) =>
      el("button", { type: "button", class: `chip ${kind}`, text: tag, title: `Insert ${tag}`, onclick: () => insertTag(tag) });
    $("script-palette").replaceChildren(
      ...[
        row("Emotions", emotions.map((e) => chip("emotion", `[${e}]`))),
        row("Sounds", sounds.map((s) => chip("sound", `{${s.name}}`))),
      ].filter(Boolean),
    );
  }

  // --- Checking -----------------------------------------------------------------------------

  // POST to `path`; a rejected Script (422 with a check body) comes back as that body.
  async function sendScript(path) {
    try {
      return await api("POST", path, request());
    } catch (error) {
      if (error.status === 422 && error.data && "ready" in error.data) return error.data;
      throw error;
    }
  }

  async function runCheck() {
    showError("");
    if (!$("script-voice").value) return showError("Save a Voice first, then pick it here.");
    showCheck(await sendScript("/scripts/check"));
  }

  function showCheck(check) {
    lastCheck = check;
    const voiceId = $("script-voice").value;
    const box = $("script-result");
    const parts = [];
    if (check.ready) {
      const count = check.segments.filter((s) => s.kind !== "vocal_effect").length;
      parts.push(el("p", { class: "ok", text: `Ready to generate: ${count} ${count === 1 ? "Segment" : "Segments"}.` }));
    } else {
      parts.push(el("p", { class: "error", text: "Fix these before generating:" }));
      const items = [
        ...check.missing_emotions.map((emotion) =>
          el(
            "li",
            {},
            el("code", { text: `[${emotion}]` }),
            ` ${voiceName()} has no ${emotion} preset. `,
            el("button", {
              type: "button",
              text: `Add ${emotion} to ${voiceName()}`,
              onclick: () => window.Voicewright.addEmotion(voiceId, emotion),
            }),
          ),
        ),
        ...check.missing_sounds.map((name) =>
          el(
            "li",
            {},
            el("code", { text: `{${name}}` }),
            " isn't in your Sound library. ",
            el("button", { type: "button", text: "Find it on Freesound", onclick: () => window.Voicewright.findSound(name) }),
          ),
        ),
        ...check.parse_errors.map((problem) =>
          el(
            "li",
            {},
            el("button", { type: "button", class: "link", text: where(problem), onclick: () => goTo(problem) }),
            `: ${problem.message}`,
          ),
        ),
      ];
      parts.push(el("ul", { class: "problems" }, ...items));
    }
    if (check.warnings.length) {
      parts.push(
        el(
          "ul",
          { class: "warnings" },
          ...check.warnings.map((warning) =>
            el(
              "li",
              {},
              el("button", { type: "button", class: "link", text: where(warning), onclick: () => goTo(warning) }),
              `: ${warning.message}`,
            ),
          ),
        ),
      );
    }
    box.replaceChildren(...parts);
  }

  // After an emotion or sound is added, a Script that was missing one is checked again.
  function recheckIfMissing() {
    if (lastCheck && !lastCheck.ready && $("script-voice").value) runCheck().catch(() => {});
  }

  // --- Generating ---------------------------------------------------------------------------

  async function generate() {
    showError("");
    if (!$("script-voice").value) return showError("Save a Voice first, then pick it here.");
    let result;
    try {
      result = await runJob("/scripts/generate", request());
    } catch (error) {
      if (error.status === 422 && error.data && "ready" in error.data) return showCheck(error.data);
      return showError(error.message);
    }
    $("script-result").replaceChildren(
      el("p", { class: "ok", text: `Done: a ${seconds(result.duration)} Output. It's at the top of Recent Outputs.` }),
    );
    lastCheck = null;
    await refreshOutputs();
    const audio = document.querySelector(`#outputs [data-output="${result.output_id}"] audio`);
    if (audio) {
      audio.scrollIntoView({ block: "nearest" });
      audio.play().catch(() => {}); // the browser may want a fresh click; the player is there
    }
  }

  // --- Outputs ------------------------------------------------------------------------------

  async function refreshOutputs() {
    const outputs = await api("GET", "/outputs");
    $("outputs").replaceChildren(...outputs.map(outputCard));
    $("no-outputs").hidden = outputs.length > 0;
    // The sidebar shows how many Outputs there are.
    document.dispatchEvent(new CustomEvent("voicewright:outputs", { detail: outputs }));
  }

  function outputCard(output) {
    const line = el("p", { class: "error", role: "alert", hidden: true });
    const save = output.saved_id
      ? el("span", { class: "saved-tag", text: "Saved" })
      : el("button", {
          type: "button",
          text: "Save",
          onclick: async (event) => {
            event.target.disabled = true;
            line.hidden = true;
            try {
              await api("POST", `/outputs/${output.id}/save`);
              await Promise.all([refreshOutputs(), refreshSaved()]);
            } catch (error) {
              line.textContent = error.message;
              line.hidden = false;
              event.target.disabled = false;
            }
          },
        });
    return el(
      "div",
      { class: "card", dataset: { output: output.id } },
      el(
        "div",
        { class: "output-meta" },
        el("strong", { text: output.voice_name }),
        el("span", { class: "muted", text: `${when(output.created)} · ${seconds(output.duration)}` }),
      ),
      el("p", { class: "excerpt", text: excerpt(output.script) }),
      player(output.audio_url),
      el(
        "div",
        { class: "row" },
        save,
        el("a", { class: "button download", href: output.audio_url, download: output.download_name, text: "Download WAV" }),
      ),
      line,
    );
  }

  async function refreshSaved() {
    const saved = await api("GET", "/saved");
    $("saved").replaceChildren(...saved.map(savedCard));
    $("no-saved").hidden = saved.length > 0;
  }

  function savedCard(saved) {
    const credits = saved.sounds.length
      ? el("p", { class: "muted" }, `Sounds: ${saved.sounds.map((s) => `{${s.name}} "${s.title}" by ${s.author} (${s.license})`).join("; ")}`)
      : null;
    return el(
      "div",
      { class: "card", dataset: { saved: saved.id } },
      el(
        "div",
        { class: "output-meta" },
        el("strong", { text: saved.voice_name }),
        el("span", { class: "muted", text: `saved ${when(saved.saved)} · ${seconds(saved.duration)}` }),
      ),
      el("p", { class: "excerpt", text: excerpt(saved.script) }),
      credits,
      player(saved.audio_url),
      el(
        "div",
        { class: "row" },
        el("a", { class: "button download", href: saved.audio_url, download: saved.download_name, text: "Download WAV" }),
        el("a", { class: "button", href: saved.record_url, target: "_blank", rel: "noopener", text: "Record (JSON)" }),
      ),
    );
  }

  // --- The cache size setting ---------------------------------------------------------------

  async function loadSettings() {
    const settings = await api("GET", "/settings");
    const [low, high] = settings.output_cache_range;
    const select = $("cache-size");
    const sizes = Array.from({ length: high - low + 1 }, (_, i) => low + i);
    select.replaceChildren(...sizes.map((n) => el("option", { value: n, text: String(n) })));
    select.value = settings.output_cache_size;
  }

  $("cache-size").addEventListener("change", async (event) => {
    $("cache-error").hidden = true;
    try {
      await api("PUT", "/settings", { output_cache_size: Number(event.target.value) });
      await refreshOutputs();
    } catch (error) {
      $("cache-error").textContent = error.message;
      $("cache-error").hidden = false;
      await loadSettings().catch(() => {});
    }
  });

  // --- Wiring -------------------------------------------------------------------------------

  $("script-check").addEventListener("click", () => runCheck().catch((error) => showError(error.message)));
  $("script-form").addEventListener("submit", (event) => {
    event.preventDefault();
    generate();
  });
  const text = $("script-text");
  text.value = recall(SAVED_SCRIPT) ?? "";
  text.addEventListener("input", () => {
    remember(SAVED_SCRIPT, text.value);
    showEditor();
  });
  // ⌘Enter (Ctrl+Enter off the Mac) generates, unless a job is already running.
  text.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      if (!$("script-generate").disabled) $("script-form").requestSubmit();
    }
  });
  // The Scripts area may be hidden when the page opens; size the box once it shows.
  window.addEventListener("hashchange", showEditor);
  window.addEventListener("resize", showEditor);
  showEditor();
  $("script-voice").addEventListener("change", () => {
    remember(SAVED_VOICE, $("script-voice").value);
    showPalette();
    lastCheck = null;
    $("script-result").replaceChildren();
  });

  document.addEventListener("voicewright:voices", (event) => {
    showVoices(event.detail);
    recheckIfMissing();
  });
  document.addEventListener("voicewright:sounds", (event) => {
    sounds = event.detail;
    showPalette();
    recheckIfMissing();
  });
  // A Script job followed from elsewhere (one already running when the page opened) ends here too.
  document.addEventListener("voicewright:job-finished", (event) => {
    if (event.detail.kind === "script") refreshOutputs().catch(() => {});
  });

  Promise.all([
    api("GET", "/voices").then(showVoices),
    refreshOutputs(),
    refreshSaved(),
    loadSettings(),
  ]).catch((error) => showError(error.message));
})();
