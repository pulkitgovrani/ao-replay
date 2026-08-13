# Spec: ao_replay/narrate.py, ao_replay/cli.py, README.md

`recap` matches the schema in `specs/SPEC_INGEST.md` / `ao_replay/fixtures/demo_recap.json` exactly — build and test against that fixture file directly, don't wait on ingest.py or render.py; other sessions are building those in parallel against the same contract.

## 1. `ao_replay/narrate.py`

Implement:

    def generate_script(recap: dict) -> str

Returns a **deterministic, template-based** narration script (plain text) — no LLM/API calls, no network, no extra dependencies. It should read like a short voiceover script someone could read aloud over a screen recording of the generated recap page. Structure:

```
[0:00] Opening line mentioning project name and agent_count, e.g. "This is what N parallel AI coding agents built in Agent Orchestrator today."
[0:xx] One beat per session in chronological created_at order — display_name, harness, what happened (spawned / PR opened / merged), derived from recap["sessions"] and recap["timeline"].
[0:xx] Closing line with the headline stat: time_saved_pct and a human phrase, e.g. "That's 60% faster than working through this one agent at a time."
```

Timestamps `[m:ss]` should be evenly paced estimates based on number of beats (e.g. ~4-6 seconds per beat) — they don't need to be exact, just monotonically increasing and reasonable for a ~60-90 second video.

## 2. `ao_replay/cli.py`

Implement an argparse-based CLI with entry point `main()`:

    ao-replay report [--db PATH] [--project ID] [--demo] [--out FILE.html] [--script-out FILE.txt]

Behavior:
- Imports `from ao_replay.ingest import load_recap`, `from ao_replay.render import render_html`, `from ao_replay.narrate import generate_script`. These modules are being built in parallel by other sessions against this exact contract — write your code against the documented function signatures (`load_recap(db_path=None, project_id=None, demo=False) -> dict`, `render_html(recap: dict) -> str`, `generate_script(recap: dict) -> str`) even if the files don't exist yet in your worktree; they will exist after merge. Do not stub or reimplement their logic.
- `--demo` forces `load_recap(demo=True)`.
- Default `--out` is `ao-replay-recap.html`, default `--script-out` is `ao-replay-script.txt`.
- Writes both files, and prints a short colored-free terminal summary: project name, agent count, time saved %, PRs merged, and the output file paths.
- Non-zero exit + clear stderr message on failure (e.g. can't find a real db and `--demo` wasn't passed and no default db exists — in that case, print a helpful message suggesting `--demo`).

Also add a thin executable wrapper `bin/ao-replay` (shell script, `chmod +x`) that does `exec python3 -m ao_replay.cli "$@"` resolved relative to the repo (use `SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)` and run from `$SCRIPT_DIR/..`), so `./bin/ao-replay report --demo` works from a fresh clone with zero install steps (stdlib only, no pip install needed).

## 3. `README.md`

Rewrite the root `README.md` (currently a stub) to include:
- What AO Replay is and why (one paragraph): turns an Agent Orchestrator session's local SQLite history into a recap page + narration script — stats on how many agents ran in parallel, time saved vs sequential work, PRs/CI outcomes, and a timeline.
- Quick start: `git clone`, `./bin/ao-replay report --demo`, open `ao-replay-recap.html`.
- Real usage: `./bin/ao-replay report` (reads `~/.ao/data/ao.db` directly, read-only).
- Note that this project was itself built using Agent Orchestrator — three parallel `claude-code` worker sessions (ingest / render / cli+narration) against a shared JSON contract, merged via AO-managed PRs. Mention it was built for **The Orchestra** hackathon.
- Zero runtime dependencies — Python 3 stdlib only.
- One sentence on privacy: it only ever reads your local `~/.ao` SQLite file read-only; nothing leaves your machine.

## Constraints

- Python 3, stdlib only (`argparse`, `json`, `sys`, `pathlib`). No pip dependencies.
- Write `ao_replay/tests/test_narrate.py` (stdlib `unittest`) that loads the demo fixture and asserts `generate_script` returns a non-empty string containing every session's `display_name` and the `time_saved_pct` figure.
- Run `python3 -m unittest ao_replay.tests.test_narrate -v` yourself and confirm it passes before finishing.
- Only touch: `ao_replay/narrate.py`, `ao_replay/cli.py`, `bin/ao-replay`, `ao_replay/tests/test_narrate.py`, `README.md`, and create `ao_replay/__init__.py` / `ao_replay/tests/__init__.py` as empty files if missing (don't overwrite them if they already exist from a parallel PR — check first).
- Open a PR when done.
