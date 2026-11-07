// The Voices area: design a Draft voice, review it, accept or discard it, and edit saved Voices.
// It talks only to the HTTP API, through common.js. User text goes in as text, never HTML.
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const errorBox = $("voices-error");

  // The Draft voice open for review, if any.
  let reviewing = null;
  // Saved Voice cards the user has opened: they stay open when the list is rebuilt.
  const openVoices = new Set();

  const { api, el, player, runJob, follow, setBusy, isBusy } = window.Voicewright;

  // Where an action's error shows: next to the control, in the errorSlot(key) rendered beside
  // it, or in the line at the top of the page when the action has no slot.
  const errorSlot = (key) =>
    el("p", { class: "error", role: "alert", hidden: true, dataset: { errorFor: key } });

  function showError(error, key) {
    const slot =
      key && [...document.querySelectorAll("[data-error-for]")].find((n) => n.dataset.errorFor === key);
    const box = slot || errorBox;
    box.textContent = error.message;
    box.hidden = false;
  }

  function clearErrors() {
    errorBox.hidden = true;
    for (const slot of document.querySelectorAll("[data-error-for]")) slot.hidden = true;
  }

  // Run an action; show what went wrong, next to `key`'s slot, instead of throwing.
  // Returns false on failure.
  async function attempt(action, key) {
    clearErrors();
    try {
      await action();
      return true;
    } catch (error) {
      // A refused request (a taken name, a job already running) changed nothing, so the page
      // stays as it is, keeping what was typed. Anything else may have changed things (a
      // failed design keeps the clips it made), so the page is reloaded first.
      if (error.status !== 409 && error.status !== 422) await refresh().catch(() => {});
      showError(error, key);
      return false;
    }
  }

  // Play the clip at `url` once the page shows it: the take just made by a click.
  function playClip(url) {
    const audio = [...document.querySelectorAll("audio")].find((a) => a.getAttribute("src") === url);
    if (!audio) return;
    audio.scrollIntoView({ block: "nearest" });
    // The browser may refuse to play without a recent click; the player is still there.
    audio.play().catch(() => {});
  }

  // --- Jobs (the bar and runJob live in common.js) ------------------------------------

  // A job may already be running when the page opens: loading the speech model at startup, or
  // a design started before the page was reloaded.
  async function followCurrentJob() {
    const job = await api("GET", "/jobs/current");
    if (job) {
      await attempt(async () => {
        await follow(job.id);
        await refresh();
      });
    }
  }

  // --- Building the page --------------------------------------------------------------------


  function jobButton(text, action, errorKey) {
    return el("button", {
      type: "button",
      text,
      dataset: { startsJob: "" },
      onclick: () => attempt(action, errorKey),
    });
  }

  // Exaggeration and cfg sliders, set to `preset`'s values; read() gives the chosen values.
  function sliders(preset) {
    const make = (label, value, max) => {
      const input = el("input", { type: "range", min: 0, max, step: 0.05, value });
      const shown = el("output", { text: Number(value).toFixed(2) });
      input.addEventListener("input", () => (shown.textContent = Number(input.value).toFixed(2)));
      return { input, node: el("label", { class: "slider" }, label, input, shown) };
    };
    const exaggeration = make("Exaggeration", preset.exaggeration, 2);
    const cfg = make("cfg", preset.cfg, 1);
    return {
      nodes: [exaggeration.node, cfg.node],
      read: () => ({ exaggeration: Number(exaggeration.input.value), cfg: Number(cfg.input.value) }),
    };
  }

  // --- Draft voices -------------------------------------------------------------------------

  async function refreshDrafts() {
    const drafts = await api("GET", "/voices/drafts");
    const list = $("drafts");
    list.replaceChildren(
      ...drafts.map((draft) =>
        el(
          "div",
          { class: "row" },
          el("span", { text: draft.description }),
          draft.missing.length
            ? el("span", { class: "muted", text: `(missing ${draft.missing.join(", ")})` })
            : null,
          el("button", { type: "button", text: "Resume", onclick: () => attempt(() => openDraft(draft.id), "drafts") }),
          el("button", { type: "button", text: "Discard", onclick: () => attempt(() => discard(draft), "drafts") }),
        ),
      ),
    );
    $("drafts-area").hidden = drafts.length === 0;
    if (reviewing && !drafts.some((draft) => draft.id === reviewing)) closeReview();
  }

  async function discard(draft) {
    if (!confirm(`Discard the Draft voice "${draft.description}" and every take?`)) return;
    await api("DELETE", `/voices/drafts/${draft.id}`);
    if (reviewing === draft.id) closeReview();
    await refreshDrafts();
  }

  function closeReview() {
    reviewing = null;
    $("review").hidden = true;
    $("review").replaceChildren();
  }

  async function openDraft(draftId) {
    const draft = await api("GET", `/voices/drafts/${draftId}`);
    reviewing = draftId;
    const review = $("review");
    review.replaceChildren(
      el("h3", { text: "Review the Draft voice" }),
      ...descriptionEditor(draft),
      ...draft.emotions.map((emotion) => draftPreset(draft, emotion)),
      acceptForm(draft),
    );
    review.hidden = false;
    return draft;
  }

  function descriptionEditor(draft) {
    const text = el("textarea", { rows: 2, maxlength: 500 });
    text.value = draft.description;
    return [
      el("label", { text: "Description" }),
      text,
      el(
        "div",
        { class: "row" },
        jobButton(
          "Redesign every preset from this description",
          async () => {
            await runJob(`/voices/drafts/${draft.id}/redesign`, { description: text.value });
            await openDraft(draft.id);
            await refreshDrafts();
          },
          `redesign-${draft.id}`,
        ),
      ),
      errorSlot(`redesign-${draft.id}`),
    ];
  }

  function draftPreset(draft, emotion) {
    const preset = draft.presets[emotion];
    const base = `/voices/drafts/${draft.id}/presets/${emotion}`;
    const key = `draft-${draft.id}-${emotion}`;
    const heading = el("strong", { text: emotion === "neutral" ? "neutral (the Voice's identity)" : emotion });
    if (!preset) {
      return el(
        "div",
        { class: "preset" },
        heading,
        el("p", { class: "muted", text: "Not designed yet." }),
        jobButton(
          "Design it",
          async () => {
            await runJob(`${base}/regenerate`);
            playClip((await openDraft(draft.id)).presets[emotion].clip_url);
            await refreshDrafts();
          },
          key,
        ),
        errorSlot(key),
      );
    }
    const designs = draft.takes.filter((t) => t.emotion === emotion && t.kind === "design");
    const previews = draft.takes.filter((t) => t.emotion === emotion && t.kind === "preview");
    const lastPreview = previews[previews.length - 1];
    const tune = sliders(preset);
    const takeChooser =
      designs.length > 1
        ? el(
            "label",
            {},
            "Take ",
            el(
              "select",
              {
                onchange: (event) =>
                  attempt(async () => {
                    await api("PUT", base, { take: event.target.value });
                    await openDraft(draft.id);
                  }, key),
              },
              ...designs.map((take) =>
                el("option", { value: take.id, text: take.id, selected: take.id === preset.take }),
              ),
            ),
          )
        : null;
    return el(
      "div",
      { class: "preset" },
      heading,
      player(preset.clip_url),
      el(
        "div",
        { class: "row" },
        takeChooser,
        jobButton(
          emotion === "neutral" ? "Regenerate the neutral clip" : "Regenerate",
          async () => {
            await runJob(`${base}/regenerate`);
            playClip((await openDraft(draft.id)).presets[emotion].clip_url);
          },
          key,
        ),
      ),
      el("div", { class: "row" }, ...tune.nodes),
      el(
        "div",
        { class: "row" },
        jobButton(
          "Hear these values",
          async () => {
            await runJob(`${base}/retune`, tune.read());
            const updated = await openDraft(draft.id);
            const previews = updated.takes.filter((t) => t.emotion === emotion && t.kind === "preview");
            playClip(previews[previews.length - 1].url);
          },
          key,
        ),
      ),
      errorSlot(key),
      lastPreview
        ? el(
            "div",
            {},
            el("span", {
              class: "muted",
              text: `Spoken at exaggeration ${lastPreview.exaggeration}, cfg ${lastPreview.cfg}:`,
            }),
            player(lastPreview.url),
          )
        : null,
    );
  }

  function acceptForm(draft) {
    const name = el("input", { type: "text", maxlength: 60, placeholder: "Old Narrator" });
    return el(
      "form",
      {
        onsubmit: (event) => {
          event.preventDefault();
          attempt(async () => {
            await api("POST", "/voices", { draft_id: draft.id, name: name.value });
            closeReview();
            await refresh();
          }, `accept-${draft.id}`);
        },
      },
      el("h3", { text: "Save to your Voices" }),
      el("label", { text: "Name" }),
      name,
      el(
        "div",
        { class: "row" },
        el("button", { type: "submit", text: "Accept", disabled: draft.missing.length > 0 }),
        draft.missing.length
          ? el("span", { class: "muted", text: "Design every preset before accepting." })
          : null,
      ),
      errorSlot(`accept-${draft.id}`),
    );
  }

  // --- Saved Voices -------------------------------------------------------------------------

  async function refreshVoices() {
    const voices = await api("GET", "/voices");
    $("voices").replaceChildren(...voices.map(savedVoice));
    $("no-voices").hidden = voices.length > 0;
    // The Scripts area offers these Voices to pick from.
    document.dispatchEvent(new CustomEvent("voicewright:voices", { detail: voices }));
  }

  function savedVoice(voice) {
    const reload = async () => {
      await refreshVoices();
      setBusy(isBusy());
    };
    return el(
      "details",
      {
        class: "card",
        open: openVoices.has(voice.id),
        ontoggle: (event) =>
          event.target.open ? openVoices.add(voice.id) : openVoices.delete(voice.id),
      },
      el("summary", {}, el("strong", { text: voice.name }), " ", el("span", { class: "muted", text: Object.keys(voice.presets).join(", ") })),
      el("p", { class: "muted", text: voice.description }),
      // A pending take shows under its emotion; one for a new emotion, above the Add form.
      ...Object.entries(voice.presets).flatMap(([emotion, preset]) => [
        savedPreset(voice, emotion, preset, reload),
        ...voice.pending.filter((take) => take.emotion === emotion).map((take) => pendingTake(voice, take, reload)),
      ]),
      ...voice.pending.filter((take) => !(take.emotion in voice.presets)).map((take) => pendingTake(voice, take, reload)),
      addPresetForm(voice, reload),
      el(
        "div",
        { class: "row" },
        el("button", {
          type: "button",
          text: `Delete ${voice.name}`,
          onclick: () =>
            attempt(async () => {
              if (!confirm(`Delete the Voice "${voice.name}" and all its clips?`)) return;
              await api("DELETE", `/voices/${voice.id}`);
              openVoices.delete(voice.id);
              await reload();
            }, `voice-${voice.id}`),
        }),
      ),
      errorSlot(`voice-${voice.id}`),
    );
  }

  function savedPreset(voice, emotion, preset, reload) {
    const base = `/voices/${voice.id}/presets/${emotion}`;
    const tune = sliders(preset);
    const locked = emotion === "neutral";
    const key = `voice-${voice.id}-${emotion}`;
    // A job here makes a pending take: show it, then play it.
    const makeTake = async (path, body) => {
      const { take } = await runJob(path, body);
      await reload();
      playClip(`/voices/${voice.id}/takes/${take}`);
    };
    return el(
      "div",
      { class: "preset" },
      el("strong", { text: emotion }),
      player(preset.clip_url),
      el("div", { class: "row" }, ...tune.nodes),
      el(
        "div",
        { class: "row" },
        jobButton("Hear these values", () => makeTake(`${base}/retune`, tune.read()), key),
        locked
          ? el("span", { class: "muted", text: "The neutral clip is locked." })
          : jobButton("Regenerate", () => makeTake(`${base}/regenerate`), key),
        locked
          ? null
          : el("button", {
              type: "button",
              text: "Remove",
              onclick: () =>
                attempt(async () => {
                  if (!confirm(`Remove the ${emotion} preset from ${voice.name}?`)) return;
                  await api("DELETE", base);
                  await reload();
                }, key),
            }),
      ),
      errorSlot(key),
    );
  }

  function pendingTake(voice, take, reload) {
    const what =
      take.kind === "preview"
        ? `New values for ${take.emotion}: exaggeration ${take.exaggeration}, cfg ${take.cfg}`
        : `New ${take.emotion} clip`;
    const key = `take-${voice.id}-${take.id}`;
    const decide = (method, path) =>
      attempt(async () => {
        await api(method, path);
        await reload();
      }, key);
    return el(
      "div",
      { class: "pending" },
      el("span", { text: `${what}. Keep it?` }),
      player(take.url),
      el(
        "div",
        { class: "row" },
        el("button", { type: "button", text: "Accept", onclick: () => decide("POST", `/voices/${voice.id}/takes/${take.id}/accept`) }),
        el("button", { type: "button", text: "Reject", onclick: () => decide("DELETE", `/voices/${voice.id}/takes/${take.id}`) }),
      ),
      errorSlot(key),
    );
  }

  function addPresetForm(voice, reload) {
    const name = el("input", { type: "text", placeholder: "angry-soft", required: true });
    const sample = el("input", { type: "text", maxlength: 500, placeholder: "Optional sample sentence" });
    const tune = sliders(voice.presets.neutral);
    const submit = el("button", { type: "submit", text: "Design it", dataset: { startsJob: "" } });
    return el(
      "form",
      {
        class: "preset",
        dataset: { addPresetFor: voice.id },
        onsubmit: (event) => {
          event.preventDefault();
          attempt(async () => {
            const { take } = await runJob(`/voices/${voice.id}/presets`, {
              name: name.value,
              sample: sample.value || null,
              ...tune.read(),
            });
            await reload();
            playClip(`/voices/${voice.id}/takes/${take}`);
          }, `add-${voice.id}`);
        },
      },
      el("strong", { text: "Add an Emotion preset" }),
      el("div", { class: "row" }, name, sample),
      el("div", { class: "row" }, ...tune.nodes),
      el("div", { class: "row" }, submit),
      errorSlot(`add-${voice.id}`),
    );
  }

  // --- Designing ----------------------------------------------------------------------------

  $("design-form").addEventListener("submit", (event) => {
    event.preventDefault();
    attempt(async () => {
      const description = $("design-description").value;
      const result = await runJob("/voices/design", { description });
      $("design-description").value = "";
      await refreshDrafts();
      await openDraft(result.draft_id);
    }, "design");
  });
  $("design-form").querySelector("button").dataset.startsJob = "";

  // For the Scripts area: a Script uses an emotion this Voice lacks. Open the Voice's card at
  // its Add an Emotion preset form, with the name filled in.
  window.Voicewright.addEmotion = async (voiceId, name) => {
    openVoices.add(voiceId);
    await refreshVoices();
    setBusy(isBusy());
    const form = [...document.querySelectorAll("form[data-add-preset-for]")].find(
      (f) => f.dataset.addPresetFor === voiceId,
    );
    if (!form) return;
    const input = form.querySelector("input");
    input.value = name;
    form.scrollIntoView({ block: "center" });
    input.focus();
  };

  async function refresh() {
    await Promise.all([refreshDrafts(), refreshVoices()]);
    if (reviewing) await openDraft(reviewing);
    setBusy(isBusy());
  }

  attempt(async () => {
    await refresh();
    await followCurrentJob();
  });
})();
