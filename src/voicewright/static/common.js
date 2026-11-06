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

  return { api, el, player };
})();
