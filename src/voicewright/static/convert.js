// The Convert area: turn an audio or video file into a standard WAV to play or download. A file
// can be chosen or dropped on the drop zone.
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const form = $("convert-form");
  const input = $("convert-file");
  const drop = $("convert-drop");
  const button = $("convert-button");
  const status = $("convert-status");
  const error = $("convert-error");
  const result = $("convert-result");
  const player = $("convert-player");
  const download = $("convert-download");
  let lastUrl = null;

  // Dropping a file on the zone puts it in the file field, as if it had been chosen.
  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("over");
    if (event.dataTransfer.files.length) input.files = event.dataTransfer.files;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = input.files[0];
    if (!file) return;
    button.disabled = true;
    error.hidden = true;
    result.hidden = true;
    status.textContent = `Converting ${file.name}…`;
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/convert", { method: "POST", body });
      if (!response.ok) {
        const problem = await response.json().catch(() => null);
        throw new Error(problem?.detail ?? `Conversion failed (HTTP ${response.status})`);
      }
      if (lastUrl) URL.revokeObjectURL(lastUrl);
      lastUrl = URL.createObjectURL(await response.blob());
      player.src = lastUrl;
      download.href = lastUrl;
      download.download = file.name.replace(/\.[^.]*$/, "") + ".wav";
      status.textContent = `Converted ${file.name}.`;
      result.hidden = false;
    } catch (problem) {
      status.textContent = "";
      error.textContent =
        problem.message === "Failed to fetch" ? "Can't reach Voicewright; is it still running?" : problem.message;
      error.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
})();
