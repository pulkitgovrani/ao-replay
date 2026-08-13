"""Deterministic, template-based narration script generation for AO Replay.

No LLM/API calls, no network access — the script is built purely from the
recap dict via string templates so the same recap always yields the same
narration.
"""

from __future__ import annotations

OPENING_SECONDS = 6
SECONDS_PER_BEAT = 7


def generate_script(recap: dict) -> str:
    """Return a plain-text voiceover script derived from ``recap``.

    ``recap`` matches the schema documented in specs/SPEC_INGEST.md /
    ao_replay/fixtures/demo_recap.json.
    """
    project_name = recap["project"]["name"]
    stats = recap["stats"]
    agent_count = stats["agent_count"]
    time_saved_pct = stats["time_saved_pct"]

    sessions = sorted(recap.get("sessions", []), key=lambda s: s["created_at"])
    timeline = recap.get("timeline", [])

    lines = []
    t = 0.0

    lines.append(
        _line(
            t,
            f"This is what {agent_count} parallel AI coding agents built in "
            f"Agent Orchestrator today, on {project_name}.",
        )
    )
    t += OPENING_SECONDS

    for session in sessions:
        events = sorted(
            (e for e in timeline if e.get("session_id") == session["id"]),
            key=lambda e: e["ts"],
        )
        lines.append(_line(t, _describe_session(session, events)))
        t += SECONDS_PER_BEAT

    lines.append(
        _line(
            t,
            f"That's {time_saved_pct}% faster than working through this one "
            f"agent at a time.",
        )
    )

    return "\n".join(lines) + "\n"


def _describe_session(session: dict, events: list) -> str:
    name = session["display_name"]
    harness = session["harness"]
    pr = session.get("pr")
    event_types = {e["type"] for e in events}

    beats = []

    if "session_created" in event_types:
        beats.append("spawned")

    if "pr_created" in event_types:
        if pr is not None:
            beats.append(f"opened PR #{pr['number']}")
        else:
            beats.append("opened a pull request")

    if any(
        e["type"] == "pr_check_recorded" and "failed" in e["label"].lower()
        for e in events
    ):
        beats.append("hit a CI failure")

    if "pr_updated" in event_types:
        if pr is not None and pr.get("state") == "merged":
            beats.append("got it merged")
        else:
            beats.append("updated the PR")

    if not beats:
        beats.append("worked quietly in the background")

    return f"{name} ({harness}) " + ", then ".join(beats) + "."


def _line(seconds: float, text: str) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    return f"[{minutes}:{secs:02d}] {text}"
