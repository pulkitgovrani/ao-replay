# Spec: ao_replay/render.py

Implement:

    def render_html(recap: dict) -> str

`recap` matches the schema in `specs/SPEC_INGEST.md` / `ao_replay/fixtures/demo_recap.json` exactly — build and test against that fixture file directly (`json.load(open("ao_replay/fixtures/demo_recap.json"))`), don't wait on ingest.py.

## What to build

A single, fully self-contained HTML document string: **inline `<style>` and `<script>` only, zero external requests** (no CDN fonts/JS/CSS, no network calls) — it must open correctly via `file://`.

Sections, top to bottom:

1. **Header** — project name (`recap.project.name`), generated timestamp, one-line subtitle like "N agents · Xm wall clock · Y% time saved".
2. **Stat tiles row** — 4-5 tiles: agents used (`stats.agent_count`), time saved (`stats.time_saved_pct`% / `stats.time_saved_seconds` formatted as e.g. "2h 55m"), PRs merged (`stats.prs_merged`/`stats.prs_opened`), lines changed (`+additions -deletions`), CI pass rate (`ci_checks_passed`/(`ci_checks_passed`+`ci_checks_failed`)).
3. **Timeline / Gantt** — one horizontal lane per entry in `recap.sessions`, a bar spanning `created_at` → `ended_at` (or "now" if null) positioned proportionally across the full `window.start`–`window.end` range, labeled with `display_name` and `harness`. Color bars by harness (a small fixed palette, distinguishable in dark mode — this is a dark-themed page). Show PR state as a small badge at the end of each bar if `session.pr` is present (e.g. "PR #2 merged").
4. **Event feed** — `recap.timeline` entries listed chronologically below the gantt, each showing a formatted time + `label`, with a small type indicator/icon distinguishing `session_created` / `pr_created` / `pr_updated` / `pr_check_recorded`.

## Design

- Dark, cinematic "replay" aesthetic (this is literally showing off a completed hackathon build). Single accent color family for bars/highlights, neutral dark background, high-contrast readable text. Keep it clean — this is what gets screen-recorded for a demo video, so it should look good full-screen in a browser window at ~1280x720 and above.
- No build step — plain HTML/CSS/vanilla JS only, output is a single string with everything inlined.
- Responsive-ish is a nice-to-have but the primary target is a normal desktop browser window; don't over-engineer.

## Constraints

- Python 3, stdlib only (`html` module for escaping is fine, `json` if needed). No pip dependencies, no Jinja2 — build the HTML via an f-string/template function, escaping any user-controlled text (`display_name`, `label`, etc.) with `html.escape`.
- Write `ao_replay/tests/test_render.py` (stdlib `unittest`) that loads the demo fixture, calls `render_html`, and asserts: output starts with `<!doctype html>` or `<html`, contains no external `http://`/`https://` resource references (no `<script src="http...`, no `<link href="http...`), and contains each session's `display_name`.
- Run `python3 -m unittest ao_replay.tests.test_render -v` yourself and confirm it passes before finishing.
- Only touch: `ao_replay/render.py`, `ao_replay/tests/test_render.py`, and create `ao_replay/__init__.py` / `ao_replay/tests/__init__.py` as empty files if missing (don't overwrite them if they already exist from a parallel PR — check first).
- Open a PR when done.
