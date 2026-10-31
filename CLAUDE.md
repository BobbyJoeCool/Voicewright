# CLAUDE.md — Working Instructions for Voicewright

## Logging Requirements

**Every time a code file is edited or created, or any file is created, log it.**

- Logs live in `DevNotes/Logs/` (gitignored: working notes, not part of the deliverable).
- One log file per build phase: `DevNotes/Logs/phase-N.md` (e.g. `phase-0.md`, `phase-1.md`).
- All work logs into the current phase's file. When a new phase starts, start a new
  `phase-N.md`; don't keep appending to the old one.
- Within a phase file, append entries; don't overwrite. Structure:
  - `# Phase N — <Phase name> Log`
  - `## Phase N.M — <Step name>` for each step within the phase
  - `### Session N.M — YYYY-MM-DD` for each working session on that step
  - A **Files created or modified** table (`| File | What it does |`), one row per file touched
  - Optional **Packages installed** and **Implementation notes** subsections when relevant

**Log file markdown conventions** (keep markdownlint-clean):

- Leave a blank line before and after every bullet list.
- Leave a blank line between a heading and any text or list that follows it.
- Do not repeat the same heading text within a file (MD024). Recurring section labels
  must be qualified with a step/session number, e.g. `#### 1.1 — Files created`,
  `#### 1.2 — Files created`.

**Also log, in the same phase file:**

- Any structural change to what the app does (behavior, data model, screen flow, or rules
  in the project spec), not just routine implementation of what's already specified. If a
  design decision changes mid-build, log the change and why.
- Any update made to spec, README, or diagram files: what was updated and why.

Routine work that matches the spec exactly needs only a one- or two-line description per
file. The bar for detail rises only when something deviated from or extended what was
already documented.

## Agent skills

### Issue tracker

GitHub Issues on `BobbyJoeCool/Voicewright` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `bug`, `enhancement`, `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` at the root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.

### External peers

`claude`: always uses the Claude CLI as the peer reviewer; model at CLI default, effort high. See `docs/agents/cross-model.json`.
