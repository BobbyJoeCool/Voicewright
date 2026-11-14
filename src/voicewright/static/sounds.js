// The Sounds area: the Sound library (play, replace, remove) and Freesound search (preview,
// check the license, pick, and name). It talks only to the HTTP API, through common.js.
(() => {
  "use strict";

  const { api, el, player } = window.Voicewright;
  const $ = (id) => document.getElementById(id);

  // The sound name being replaced, while the user picks a Freesound result for it.
  let replacing = null;
  // The search on show: its query, the name to offer for a result (from the query, unless the
  // search is for a named sound a Script is missing), the last page loaded, and the results.
  let search = null;

  // --- Small pieces -------------------------------------------------------------------------

  const seconds = (value) => `${Number(value).toFixed(1)} s`;

  // What a license asks of the user, so they can judge it before picking (spec story 28).
  function licenseNote(license) {
    const text = license.toLowerCase();
    if (text.includes("creative commons 0")) return "No credit needed.";
    if (text.includes("noncommercial")) return "Credit the author; not for commercial use.";
    if (text.includes("attribution")) return "Credit the author.";
    if (text.includes("sampling+")) return "Credit the author; read the Sampling+ terms.";
    return "Check this license before using the sound.";
  }

  // A sound name from free text: lowercase letters, digits, - and _ ("Door slam!" → door-slam).
  const nameFrom = (text) =>
    text
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^[-_]+|[-_]+$/g, "")
      .slice(0, 60);

  const errorLine = () => el("p", { class: "error", role: "alert", hidden: true });

  function show(line, error) {
    line.textContent = error.message;
    line.hidden = false;
  }

  // A button that runs `action` once at a time: disabled with `busyText` until it ends. An error
  // shows in `line`. Returns the button.
  function actionButton(text, busyText, line, action) {
    const button = el("button", { type: "button", text });
    button.addEventListener("click", async () => {
      line.hidden = true;
      button.disabled = true;
      button.textContent = busyText;
      try {
        await action();
      } catch (error) {
        show(line, error);
      } finally {
        button.disabled = false;
        button.textContent = text;
      }
    });
    return button;
  }

  // --- The Sound library --------------------------------------------------------------------

  async function refreshLibrary() {
    const sounds = await api("GET", "/sounds");
    $("sounds").replaceChildren(...sounds.map(librarySound));
    $("no-sounds").hidden = sounds.length > 0;
    // The Scripts area rechecks a Script that was missing a sound.
    document.dispatchEvent(new CustomEvent("voicewright:sounds", { detail: sounds }));
    return sounds;
  }

  function librarySound(sound) {
    const { credit } = sound;
    const line = errorLine();
    return el(
      "div",
      { class: "preset", dataset: { sound: sound.name } },
      el("strong", { text: `{${sound.name}}` }),
      player(sound.audio_url),
      el(
        "p",
        { class: "muted" },
        `"${credit.title}" by ${credit.author} · ${credit.license} · ${seconds(sound.duration)} · `,
        el("a", { href: credit.source, target: "_blank", rel: "noopener", text: "on Freesound" }),
      ),
      el(
        "div",
        { class: "row" },
        el("button", { type: "button", text: "Replace", onclick: () => startReplacing(sound.name) }),
        actionButton("Remove", "Removing…", line, async () => {
          const sure = confirm(
            `Remove {${sound.name}} from the Sound library? Scripts that use it won't run until a sound is saved under that name again.`,
          );
          if (!sure) return;
          await api("DELETE", `/sounds/${sound.name}`);
          if (replacing === sound.name) stopReplacing();
          await refreshLibrary();
        }),
      ),
      line,
    );
  }

  // --- Replacing ----------------------------------------------------------------------------

  function startReplacing(name) {
    replacing = name;
    const banner = $("sound-replacing");
    banner.replaceChildren(
      el("span", { text: `Pick a Freesound result to replace {${name}}. The name stays the same. ` }),
      el("button", { type: "button", text: "Cancel", onclick: stopReplacing }),
    );
    banner.hidden = false;
    const query = $("sound-query");
    if (!query.value.trim()) query.value = name.replace(/[-_]+/g, " ");
    rerenderResults();
    $("sound-search-heading").scrollIntoView({ block: "start" });
    query.focus();
  }

  function stopReplacing() {
    replacing = null;
    $("sound-replacing").hidden = true;
    rerenderResults();
  }

  // --- Searching Freesound ------------------------------------------------------------------

  async function runSearch(query, page, name = null) {
    const error = $("sound-search-error");
    const status = $("sound-search-status");
    error.hidden = true;
    status.textContent = page === 1 ? "Searching Freesound…" : "Loading more…";
    $("sound-more").hidden = true;
    try {
      const found = await api("GET", `/sounds/search?q=${encodeURIComponent(query)}&page=${page}`);
      if (page === 1) search = { query, name: name || nameFrom(query), results: [] };
      search.page = page;
      search.results.push(...found.results);
      search.hasNext = found.has_next;
      status.textContent = found.count
        ? `${found.count} ${found.count === 1 ? "result" : "results"} for "${query}" on Freesound.`
        : `Nothing on Freesound for "${query}". Try other words.`;
      rerenderResults();
    } catch (problem) {
      status.textContent = "";
      showSearchError(problem);
    }
  }

  function showSearchError(problem) {
    const error = $("sound-search-error");
    error.replaceChildren(problem.message);
    // No key yet: make the sign-up page one click away.
    if (problem.data && problem.data.reason === "no_api_key") {
      error.append(
        " ",
        el("a", {
          href: "https://freesound.org/apiv2/apply",
          target: "_blank",
          rel: "noopener",
          text: "Get a Freesound API key",
        }),
      );
    }
    error.hidden = false;
  }

  function rerenderResults() {
    const results = search ? search.results : [];
    $("sound-results").replaceChildren(...results.map((result) => searchResult(result, search.name)));
    $("sound-more").hidden = !(search && search.hasNext);
  }

  function searchResult(result, offeredName) {
    const line = errorLine();
    const done = el("p", { class: "muted", hidden: true });
    const name = el("input", {
      type: "text",
      maxlength: 60,
      value: offeredName,
      "aria-label": `Name for ${result.title}`,
    });
    const keep = replacing
      ? actionButton(`Replace {${replacing}}`, "Replacing…", line, async () => {
          const target = replacing;
          await api("PUT", `/sounds/${target}`, { freesound_id: result.id });
          stopReplacing();
          await refreshLibrary();
          done.textContent = `Replaced {${target}} with this sound.`;
          done.hidden = false;
        })
      : actionButton("Add", "Adding…", line, async () => {
          const sound = await api("POST", "/sounds", { freesound_id: result.id, name: name.value });
          await refreshLibrary();
          done.textContent = `Added as {${sound.name}}.`;
          done.hidden = false;
        });
    return el(
      "div",
      { class: "card", dataset: { freesoundId: result.id } },
      el("strong", { text: result.title }),
      el(
        "p",
        { class: "muted" },
        `by ${result.author} · ${seconds(result.duration)} · `,
        el("a", { href: result.url, target: "_blank", rel: "noopener", text: "on Freesound" }),
      ),
      el("p", {}, `License: ${result.license}. `, el("span", { class: "license-note", text: licenseNote(result.license) })),
      player(result.preview_url),
      el("div", { class: "row" }, replacing ? null : name, keep),
      line,
      done,
    );
  }

  $("sound-search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const query = $("sound-query").value.trim();
    if (query) runSearch(query, 1);
  });
  $("sound-more").addEventListener("click", () => runSearch(search.query, search.page + 1));

  // For the Scripts area (step 4.5): a Script names a missing sound; search Freesound for it.
  window.Voicewright.findSound = (name) => {
    $("sound-query").value = name.replace(/[-_]+/g, " ");
    $("sound-search-heading").scrollIntoView({ block: "start" });
    runSearch($("sound-query").value, 1, name);
  };

  refreshLibrary().catch((error) => {
    $("no-sounds").textContent = error.message;
  });
})();
