// Helpers shared by the page's areas (Voices, Sounds): talking to the API and building elements.
// Anything the user typed goes into the page as text, never HTML.
window.Voicewright = (() => {
  "use strict";

  // Call the API; returns the JSON reply (null for 204). A failure throws an Error whose message
  // is one plain sentence, with `status` and the reply's `data` (e.g. a 503's `reason`).
  async function api(method, path, body) {
    let response;
    try {
      response = await fetch(path, {
        method,
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new Error("Can't reach Voicewright; is it still running?");
    }
    if (response.status === 204) return null;
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(describeProblem(data, response.status));
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  function describeProblem(data, status) {
    const detail = data && data.detail;
    if (typeof detail === "string") return sentence(detail);
    if (Array.isArray(detail) && detail.length) {
      // FastAPI's validation errors: "Value error, describe the voice, …"
      return sentence(String(detail[0].msg).replace(/^Value error, /, ""));
    }
    return `Something went wrong (HTTP ${status}).`;
  }

  const sentence = (text) => {
    const capitalized = text.charAt(0).toUpperCase() + text.slice(1);
    return /[.!?]$/.test(capitalized) ? capitalized : capitalized + ".";
  };

  // el("button", {onclick, text: "Go"}, child, …): an element; `text` is set as text, never HTML.
  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (key === "dataset") Object.assign(node.dataset, value);
      else if (value === true) node.setAttribute(key, "");
      else if (value !== false && value !== undefined) node.setAttribute(key, value);
    }
    node.append(...children.filter((child) => child !== null && child !== undefined));
    return node;
  }

  const player = (url) => el("audio", { controls: true, preload: "none", src: url });

  // --- Jobs: one long operation at a time, shown in the bar at the top of the page ----------

  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

  function showJob(job) {
    const { step, total, message } = job.progress;
    // Step `total` of `total` is the wrap-up after the last step (e.g. reloading the speech
    // model): it gets no number, since "step 5 of 4" reads as a bug. A Script counts Segments.
    const counted = total && step < total;
    const unit = job.kind === "script" ? "Segment" : "step";
    $("job-message").textContent = counted ? `${message} (${unit} ${step + 1} of ${total})` : message;
    const bar = $("job-progress");
    if (total) {
      bar.max = total;
      bar.value = Math.min(step, total);
    } else {
      bar.removeAttribute("value"); // an indeterminate bar
    }
    $("job").hidden = false;
    setBusy(true);
  }

  function hideJob() {
    $("job").hidden = true;
    setBusy(false);
  }

  // While a job runs, buttons that would start another are disabled: the server would say 409.
  function setBusy(busy) {
    for (const button of document.querySelectorAll("button[data-starts-job]")) {
      button.disabled = busy;
    }
  }

  // Follow a job to its end and return its result; a failed job throws its error. Every area
  // hears when a job ends ("voicewright:job-finished"), to refresh what it shows.
  async function follow(jobId) {
    try {
      for (;;) {
        const job = await api("GET", `/jobs/${jobId}`);
        if (job.state !== "running") {
          hideJob();
          document.dispatchEvent(new CustomEvent("voicewright:job-finished", { detail: job }));
          if (job.state === "failed") throw new Error(job.error);
          return job.result;
        }
        showJob(job);
        await sleep(700);
      }
    } finally {
      hideJob();
    }
  }

  // Start a job with POST `path`, follow it to the end, and return its result.
  async function runJob(path, body) {
    setBusy(true); // at once, so a second click can't start a second job
    try {
      const { job_id } = await api("POST", path, body);
      return await follow(job_id);
    } finally {
      hideJob();
    }
  }

  const isBusy = () => !$("job").hidden;

  return { api, el, player, runJob, follow, setBusy, isBusy };
})();
