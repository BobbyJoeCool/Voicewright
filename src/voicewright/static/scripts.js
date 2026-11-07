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

  function showVoices(voices) {
    const select = $("script-voice");
    const chosen = select.value || localStorage.getItem(SAVED_VOICE);
    select.replaceChildren(...voices.map((v) => el("option", { value: v.id, text: v.name })));
    if (voices.some((v) => v.id === chosen)) select.value = chosen;
    $("script-no-voices").hidden = voices.length > 0;
    select.hidden = voices.length === 0;
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
  }

  function outputCard(output) {
    const line = el("p", { class: "error", role: "alert", hidden: true });
    const save = output.saved_id
      ? el("span", { class: "muted", text: "Saved" })
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
      el("strong", { text: output.voice_name }),
      el("span", { class: "muted", text: ` · ${when(output.created)} · ${seconds(output.duration)}` }),
      el("p", { class: "muted", text: excerpt(output.script) }),
      player(output.audio_url),
      el(
        "div",
        { class: "row" },
        save,
        el("a", { href: output.audio_url, download: output.download_name, text: "Download WAV" }),
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
      el("strong", { text: saved.voice_name }),
      el("span", { class: "muted", text: ` · saved ${when(saved.saved)} · ${seconds(saved.duration)}` }),
      el("p", { class: "muted", text: excerpt(saved.script) }),
      credits,
      player(saved.audio_url),
      el(
        "div",
        { class: "row" },
        el("a", { href: saved.audio_url, download: saved.download_name, text: "Download WAV" }),
        el("a", { href: saved.record_url, target: "_blank", rel: "noopener", text: "Record (JSON)" }),
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
  $("script-text").value = localStorage.getItem(SAVED_SCRIPT) ?? "";
  $("script-text").addEventListener("input", () => localStorage.setItem(SAVED_SCRIPT, $("script-text").value));
  $("script-voice").addEventListener("change", () => {
    localStorage.setItem(SAVED_VOICE, $("script-voice").value);
    lastCheck = null;
    $("script-result").replaceChildren();
  });

  document.addEventListener("voicewright:voices", (event) => {
    showVoices(event.detail);
    recheckIfMissing();
  });
  document.addEventListener("voicewright:sounds", recheckIfMissing);
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
