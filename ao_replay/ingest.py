"""Build an AO Replay recap dict from AO's local SQLite database or a demo fixture."""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_recap.json"
DEFAULT_DB_PATH = Path.home() / ".ao" / "data" / "ao.db"


def load_recap(db_path: str | None = None, project_id: str | None = None, demo: bool = False) -> dict:
    if demo:
        return _load_fixture()

    if db_path is not None:
        if not os.path.exists(db_path):
            return _load_fixture()
        resolved_path = db_path
    else:
        if not DEFAULT_DB_PATH.exists():
            return _load_fixture()
        resolved_path = str(DEFAULT_DB_PATH)

    conn = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return _build_recap(conn, project_id)
    finally:
        conn.close()


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# --- datetime helpers -------------------------------------------------

# AO's Go daemon stores timestamps as time.Time's default String() format,
# e.g. "2026-08-13 07:36:32.196718 +0000 UTC" — not Python-isoformat-parseable.
_GO_TS_RE = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"(?:\s*(?P<offset>[+-]\d{2}:?\d{2}))?"
    r"(?:\s*\w+)?$"
)


def _parse_dt(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = _GO_TS_RE.match(text)
    if m:
        text = m.group("base").replace(" ", "T", 1)
        offset = m.group("offset")
        if offset:
            if ":" not in offset:
                offset = offset[:3] + ":" + offset[3:]
            text += offset
    else:
        if "T" not in text and " " in text:
            text = text.replace(" ", "T", 1)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt):
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now():
    return datetime.now(timezone.utc)


# --- schema helpers -----------------------------------------------------

def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


# --- recap assembly -------------------------------------------------------

def _build_recap(conn, project_id):
    project = _load_project(conn, project_id)
    pid = project["id"]

    session_rows = _load_session_rows(conn, pid)
    sessions, pr_rows, spans = _build_sessions(conn, session_rows)
    stats, window = _build_stats(conn, sessions, pr_rows, spans)
    timeline = _build_timeline(conn, pid)

    return {
        "project": project,
        "generated_at": _iso(_now()),
        "window": window,
        "stats": stats,
        "sessions": sessions,
        "timeline": timeline,
    }


def _load_project(conn, project_id):
    if not _table_exists(conn, "projects"):
        return {"id": project_id or "", "name": ""}

    if project_id:
        row = conn.execute(
            "SELECT id, display_name FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    else:
        row = conn.execute("SELECT id, display_name FROM projects LIMIT 1").fetchone()

    if row is None:
        return {"id": project_id or "", "name": ""}
    return {"id": row["id"], "name": row["display_name"] or ""}


def _load_session_rows(conn, project_id):
    if not _table_exists(conn, "sessions"):
        return []
    return conn.execute(
        """
        SELECT id, display_name, harness, kind, branch, activity_state,
               is_terminated, created_at, updated_at
        FROM sessions
        WHERE project_id = ?
        ORDER BY created_at ASC
        """,
        (project_id,),
    ).fetchall()


def _load_pr_for_session(conn, session_id):
    if not _table_exists(conn, "pr"):
        return None
    return conn.execute(
        """
        SELECT url, number, pr_state, ci_state, additions, deletions, changed_files
        FROM pr
        WHERE session_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()


def _build_sessions(conn, rows):
    """Return (session dicts, matched pr rows, (created, end) spans for window/wall-clock calc)."""
    sessions = []
    pr_rows = []
    spans = []
    now = _now()

    for row in rows:
        created_at = _parse_dt(row["created_at"])
        is_terminated = bool(row["is_terminated"])
        ended_dt = _parse_dt(row["updated_at"]) if is_terminated else None
        span_end = ended_dt if ended_dt is not None else now

        duration_seconds = 0.0
        if created_at is not None:
            duration_seconds = max(0.0, (span_end - created_at).total_seconds())
            spans.append((created_at, span_end))

        pr_row = _load_pr_for_session(conn, row["id"])
        pr = None
        if pr_row is not None:
            pr = {
                "number": pr_row["number"],
                "state": pr_row["pr_state"],
                "ci_state": pr_row["ci_state"],
                "additions": pr_row["additions"] or 0,
                "deletions": pr_row["deletions"] or 0,
            }
            pr_rows.append(pr_row)

        sessions.append(
            {
                "id": row["id"],
                "display_name": row["display_name"] or "",
                "harness": row["harness"] or "",
                "kind": row["kind"] or "",
                "branch": row["branch"] or "",
                "created_at": _iso(created_at),
                "ended_at": _iso(ended_dt),
                "duration_seconds": duration_seconds,
                "activity_state": row["activity_state"] or "",
                "is_terminated": is_terminated,
                "pr": pr,
            }
        )

    return sessions, pr_rows, spans


def _count_ci_checks(conn, pr_urls):
    if not pr_urls or not _table_exists(conn, "pr_checks"):
        return 0, 0
    placeholders = ",".join("?" for _ in pr_urls)
    passed = conn.execute(
        f"SELECT COUNT(*) FROM pr_checks WHERE pr_url IN ({placeholders}) AND status = 'passed'",
        pr_urls,
    ).fetchone()[0]
    failed = conn.execute(
        f"SELECT COUNT(*) FROM pr_checks WHERE pr_url IN ({placeholders}) AND status = 'failed'",
        pr_urls,
    ).fetchone()[0]
    return passed, failed


def _build_stats(conn, sessions, pr_rows, spans):
    now = _now()
    if spans:
        window_start = min(start for start, _ in spans)
        window_end = max(end for _, end in spans)
    else:
        window_start = now
        window_end = now

    wall_clock_seconds = max(0.0, (window_end - window_start).total_seconds())
    cumulative_agent_seconds = sum(s["duration_seconds"] for s in sessions)
    time_saved_seconds = cumulative_agent_seconds - wall_clock_seconds
    time_saved_pct = (
        round((time_saved_seconds / cumulative_agent_seconds) * 100, 1)
        if cumulative_agent_seconds > 0
        else 0.0
    )

    harnesses = {}
    for s in sessions:
        name = s["harness"] or "unknown"
        harnesses[name] = harnesses.get(name, 0) + 1

    prs_opened = len(pr_rows)
    prs_merged = sum(1 for r in pr_rows if r["pr_state"] == "merged")
    additions = sum(r["additions"] or 0 for r in pr_rows)
    deletions = sum(r["deletions"] or 0 for r in pr_rows)
    files_changed = sum(r["changed_files"] or 0 for r in pr_rows)

    pr_urls = [r["url"] for r in pr_rows if r["url"] is not None]
    ci_checks_passed, ci_checks_failed = _count_ci_checks(conn, pr_urls)

    stats = {
        "agent_count": len(sessions),
        "harnesses": harnesses,
        "wall_clock_seconds": wall_clock_seconds,
        "cumulative_agent_seconds": cumulative_agent_seconds,
        "time_saved_seconds": time_saved_seconds,
        "time_saved_pct": time_saved_pct,
        "sessions_total": len(sessions),
        "prs_opened": prs_opened,
        "prs_merged": prs_merged,
        "additions": additions,
        "deletions": deletions,
        "files_changed": files_changed,
        "ci_checks_passed": ci_checks_passed,
        "ci_checks_failed": ci_checks_failed,
        # TODO: tokens_total/cost_usd would require joining model_usage_events ->
        # usage_bindings back to a session/project, and that join isn't spelled
        # out unambiguously in the schema notes. Returning 0/null rather than
        # guessing at the join.
        "tokens_total": 0,
        "cost_usd": None,
    }
    window = {"start": _iso(window_start), "end": _iso(window_end)}
    return stats, window


def _event_label(event_type, payload):
    data = {}
    if payload:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}

    if event_type == "session_created":
        name = data.get("display_name") or data.get("session_id") or "session"
        harness = data.get("harness")
        return f"{name} spawned ({harness})" if harness else f"{name} spawned"

    if event_type == "pr_created":
        number = data.get("number")
        title = data.get("title")
        if number and title:
            return f"PR #{number} opened: {title}"
        if number:
            return f"PR #{number} opened"
        return "PR opened"

    if event_type == "pr_updated":
        number = data.get("number")
        state = data.get("state") or data.get("pr_state")
        if number and state:
            return f"PR #{number} {state}"
        if number:
            return f"PR #{number} updated"
        return "PR updated"

    if event_type == "pr_check_recorded":
        status = data.get("status")
        number = data.get("number")
        name = data.get("name") or data.get("check")
        parts = [f"CI {status}" if status else "CI check recorded"]
        if number:
            parts.append(f"on PR #{number}")
        if name:
            parts.append(f"({name})")
        return " ".join(parts)

    return event_type.replace("_", " ") if event_type else "event"


def _build_timeline(conn, project_id):
    if not _table_exists(conn, "change_log"):
        return []

    rows = conn.execute(
        """
        SELECT session_id, event_type, payload, created_at
        FROM change_log
        WHERE project_id = ?
        ORDER BY created_at ASC
        """,
        (project_id,),
    ).fetchall()

    timeline = []
    for row in rows:
        timeline.append(
            {
                "ts": _iso(_parse_dt(row["created_at"])),
                "session_id": row["session_id"],
                "type": row["event_type"],
                "label": _event_label(row["event_type"], row["payload"]),
            }
        )
    return timeline
