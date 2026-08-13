# Spec: ao_replay/ingest.py

Implement:

    def load_recap(db_path: str | None = None, project_id: str | None = None, demo: bool = False) -> dict

## Behavior

- If `demo=True`, or `db_path` is given but the file doesn't exist, or `db_path` is `None` and the default AO db (`~/.ao/data/ao.db`) doesn't exist: load and return the JSON at `ao_replay/fixtures/demo_recap.json` (already committed) parsed as a dict, unchanged.
- Otherwise, open the SQLite file at `db_path` (default: `~/.ao/data/ao.db`) **read-only** using stdlib `sqlite3` only (`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`), and build a dict with **exactly** this shape (fixed contract other modules depend on — do not rename keys):

```
{
  "project": {"id": str, "name": str},
  "generated_at": iso8601 str (current UTC time),
  "window": {"start": iso8601 str, "end": iso8601 str},
  "stats": {
    "agent_count": int,
    "harnesses": {"claude-code": int, ...},
    "wall_clock_seconds": float,
    "cumulative_agent_seconds": float,
    "time_saved_seconds": float,
    "time_saved_pct": float,
    "sessions_total": int,
    "prs_opened": int,
    "prs_merged": int,
    "additions": int,
    "deletions": int,
    "files_changed": int,
    "ci_checks_passed": int,
    "ci_checks_failed": int,
    "tokens_total": int,
    "cost_usd": float | null
  },
  "sessions": [
    {"id": str, "display_name": str, "harness": str, "kind": str, "branch": str,
     "created_at": iso8601, "ended_at": iso8601 | null, "duration_seconds": float,
     "activity_state": str, "is_terminated": bool,
     "pr": {"number": int, "state": str, "ci_state": str, "additions": int, "deletions": int} | null}
  ],
  "timeline": [
    {"ts": iso8601, "session_id": str | null, "type": str, "label": str}
  ]
}
```

`timeline` is built from `change_log` rows (`project_id, session_id, event_type, payload, created_at`), ordered by `created_at` ascending, with `label` a short human-readable sentence derived from `event_type` + `payload`. Include at least: `session_created`, `pr_created`, `pr_updated`, `pr_check_recorded`.

## Real AO SQLite schema (relevant columns)

- `projects(id, path, display_name, ...)`
- `sessions(id, project_id, num, kind CHECK IN ('worker','orchestrator'), harness, activity_state, activity_last_at, is_terminated, branch, created_at, updated_at, display_name, ...)`
- `pr(url, session_id, number, pr_state CHECK IN ('draft','open','merged','closed'), ci_state, review_decision, mergeability, additions, deletions, changed_files, updated_at, created_at_provider, merged_at_provider, ...)`
- `pr_checks(pr_url, name, commit_hash, status CHECK IN ('unknown','queued','in_progress','passed','failed','skipped','cancelled'), created_at, ...)`
- `change_log(seq PK, project_id, session_id, event_type, payload JSON text, created_at)` — canonical event stream, ordered by `seq`/`created_at`
- `model_usage_events(id, binding_id, usage_source_id, model_id, input_tokens, output_tokens, ...)` joined through `usage_bindings(id, ...)` — if this join is non-trivial/ambiguous, return `0`/`null` for `tokens_total`/`cost_usd` rather than guess; leave a `# TODO` comment.

Filter everything by `project_id` (default: the single row in `projects`, or the one matching `project_id` if given). A session is "ended" at its `updated_at` if `is_terminated` is true, else `ended_at` is `null` (use `now()` only for the `duration_seconds` calc in that case).

## Constraints

- Python 3, **stdlib only** (`sqlite3`, `json`, `datetime`, `os`, `pathlib`). No pip dependencies.
- Handle empty/missing tables/rows gracefully — return zeros/empty lists, never raise, except on genuinely corrupt input.
- Write unit tests in `ao_replay/tests/test_ingest.py` (stdlib `unittest`) that:
  1. Call `load_recap(demo=True)` and assert the returned dict equals the fixture content.
  2. Build a tiny temporary SQLite db in a temp dir with 1-2 rows in `projects`/`sessions`/`pr`/`pr_checks`/`change_log` (minimal columns needed, matching real schema), call `load_recap(db_path=that db)`, and assert stats are computed correctly (e.g. `time_saved_seconds`, `prs_merged` counts).
- Run `python3 -m unittest ao_replay.tests.test_ingest -v` yourself and confirm it passes before finishing.
- Only touch: `ao_replay/ingest.py`, `ao_replay/tests/test_ingest.py`, and create `ao_replay/__init__.py` / `ao_replay/tests/__init__.py` as empty files if missing.
- Open a PR when done.
