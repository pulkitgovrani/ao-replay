"""Render an AO Replay recap dict into a single self-contained HTML document."""

import html
from datetime import datetime, timezone

# Categorical palette, dark-surface steps, fixed order (see dataviz skill palette.md).
_CATEGORICAL = [
    "#3987e5",  # blue
    "#d95926",  # orange
    "#199e70",  # aqua
    "#c98500",  # yellow
    "#d55181",  # magenta
    "#008300",  # green
    "#9085e9",  # violet
    "#e66767",  # red
]

# Fixed, reserved status scale (never themed).
_STATUS_GOOD = "#0ca30c"
_STATUS_WARNING = "#fab219"
_STATUS_SERIOUS = "#ec835a"
_STATUS_CRITICAL = "#d03b3b"

_PR_STATE_COLOR = {
    "merged": _STATUS_GOOD,
    "open": _STATUS_WARNING,
    "draft": _STATUS_WARNING,
    "closed": _STATUS_CRITICAL,
}

_EVENT_ICON = {
    "session_created": "◎",  # bullseye
    "pr_created": "◆",  # diamond
    "pr_updated": "◈",  # diamond w/ dot
    "pr_check_recorded": "✓",  # check
}


def _e(value):
    return html.escape(str(value if value is not None else ""))


def _parse_ts(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _fmt_duration(seconds):
    total = int(round(max(seconds or 0, 0)))
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    parts = []
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _fmt_dt(ts):
    return _parse_ts(ts).strftime("%b %d, %Y %H:%M UTC")


def _fmt_time(ts):
    return _parse_ts(ts).strftime("%H:%M:%S")


def _fmt_int(n):
    return f"{int(n):,}"


def _harness_colors(sessions):
    colors = {}
    for session in sessions:
        harness = session.get("harness") or "unknown"
        if harness not in colors:
            colors[harness] = _CATEGORICAL[len(colors) % len(_CATEGORICAL)]
    return colors


def _render_stat_tile(label, value, sub=""):
    sub_html = f'<div class="stat-sub">{_e(sub)}</div>' if sub else ""
    return f"""
        <div class="stat-tile">
          <div class="stat-label">{_e(label)}</div>
          <div class="stat-value">{_e(value)}</div>
          {sub_html}
        </div>"""


def _render_stats(stats):
    time_saved_pct = stats.get("time_saved_pct", 0) or 0
    time_saved_seconds = stats.get("time_saved_seconds", 0) or 0
    prs_merged = stats.get("prs_merged", 0) or 0
    prs_opened = stats.get("prs_opened", 0) or 0
    additions = stats.get("additions", 0) or 0
    deletions = stats.get("deletions", 0) or 0
    passed = stats.get("ci_checks_passed", 0) or 0
    failed = stats.get("ci_checks_failed", 0) or 0
    total_checks = passed + failed
    ci_rate = (passed / total_checks * 100) if total_checks else 0.0

    tiles = [
        _render_stat_tile("Agents used", _fmt_int(stats.get("agent_count", 0))),
        _render_stat_tile(
            "Time saved",
            f"{time_saved_pct:.1f}%",
            f"{_fmt_duration(time_saved_seconds)} saved",
        ),
        _render_stat_tile(
            "PRs merged",
            f"{_fmt_int(prs_merged)}/{_fmt_int(prs_opened)}",
            "opened → merged",
        ),
        _render_stat_tile(
            "Lines changed",
            f"+{_fmt_int(additions)} −{_fmt_int(deletions)}",
        ),
        _render_stat_tile(
            "CI pass rate",
            f"{ci_rate:.0f}%",
            f"{_fmt_int(passed)}/{_fmt_int(total_checks)} checks",
        ),
    ]
    return f'<section class="stats">{"".join(tiles)}</section>'


def _render_timeline(recap, harness_colors):
    window = recap.get("window") or {}
    sessions = recap.get("sessions") or []
    if not window.get("start") or not window.get("end") or not sessions:
        return '<section class="gantt"><h2>Timeline</h2><p class="empty">No sessions.</p></section>'

    win_start = _parse_ts(window["start"])
    win_end = _parse_ts(window["end"])
    span = (win_end - win_start).total_seconds() or 1.0
    now = datetime.now(timezone.utc)

    def pct(dt):
        return max(0.0, min(100.0, (dt - win_start).total_seconds() / span * 100.0))

    rows = []
    for session in sessions:
        start_dt = _parse_ts(session["created_at"])
        end_raw = session.get("ended_at")
        end_dt = _parse_ts(end_raw) if end_raw else max(now, win_end)

        left = pct(start_dt)
        right = pct(end_dt)
        width = max(right - left, 0.6)

        color = harness_colors.get(session.get("harness") or "unknown", _CATEGORICAL[0])
        pr = session.get("pr")
        badge_html = ""
        if pr:
            state = pr.get("state", "")
            badge_color = _PR_STATE_COLOR.get(state, _STATUS_WARNING)
            badge_html = (
                f'<span class="pr-badge" style="border-color:{badge_color};color:{badge_color}">'
                f"PR #{_e(pr.get('number'))} {_e(state)}</span>"
            )

        title = (
            f"{session.get('display_name', '')} ({session.get('harness', '')})\\n"
            f"{session.get('created_at', '')} → {end_raw or 'now'}"
        )

        rows.append(f"""
        <div class="gantt-row">
          <div class="gantt-label">
            <span class="gantt-dot" style="background:{color}"></span>
            <span class="gantt-name">{_e(session.get('display_name'))}</span>
            <span class="gantt-harness">{_e(session.get('harness'))}</span>
          </div>
          <div class="gantt-track">
            <div class="gantt-bar" title="{_e(title)}"
                 style="left:{left:.3f}%;width:{width:.3f}%;background:{color}"></div>
            {badge_html}
          </div>
        </div>""")

    legend_html = ""
    if len(harness_colors) > 1:
        swatches = "".join(
            f'<span class="legend-item"><span class="legend-swatch" style="background:{color}"></span>{_e(harness)}</span>'
            for harness, color in harness_colors.items()
        )
        legend_html = f'<div class="legend">{swatches}</div>'

    axis_html = (
        f'<div class="gantt-axis"><span>{_e(_fmt_time(window["start"]))}</span>'
        f'<span>{_e(_fmt_time(window["end"]))}</span></div>'
    )

    return f"""
    <section class="gantt">
      <h2>Timeline</h2>
      {legend_html}
      <div class="gantt-body">{"".join(rows)}</div>
      {axis_html}
    </section>"""


def _render_events(timeline):
    if not timeline:
        return '<section class="events"><h2>Event feed</h2><p class="empty">No events.</p></section>'

    items = []
    for event in timeline:
        event_type = event.get("type", "")
        icon = _EVENT_ICON.get(event_type, "•")
        label_lower = (event.get("label") or "").lower()
        check_failed = event_type == "pr_check_recorded" and "fail" in label_lower
        if check_failed:
            icon = "✗"
            color = _STATUS_CRITICAL
        elif event_type in ("pr_updated", "pr_check_recorded"):
            color = _STATUS_GOOD
        elif event_type == "pr_created":
            color = _CATEGORICAL[1]
        else:
            color = _CATEGORICAL[0]

        items.append(f"""
        <li class="event-row">
          <span class="event-icon" style="color:{color}">{icon}</span>
          <span class="event-time">{_e(_fmt_time(event.get('ts')))}</span>
          <span class="event-type">{_e(event_type)}</span>
          <span class="event-label">{_e(event.get('label'))}</span>
        </li>""")

    return f"""
    <section class="events">
      <h2>Event feed</h2>
      <ul class="event-list">{"".join(items)}</ul>
    </section>"""


_STYLE = """
:root {
  color-scheme: dark;
  --page-plane: #0d0d0d;
  --surface-1: #1a1a19;
  --surface-2: #222221;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --muted: #898781;
  --gridline: #2c2c2a;
  --baseline: #383835;
  --border: rgba(255, 255, 255, 0.10);
  --accent: #3987e5;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--page-plane);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
.viz-root {
  max-width: 1120px;
  margin: 0 auto;
  padding: 40px 32px 64px;
}
header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 24px;
  margin-bottom: 28px;
}
header h1 {
  margin: 0 0 6px;
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
header .timestamp {
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 10px;
}
header .subtitle {
  color: var(--text-secondary);
  font-size: 16px;
}
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 2px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 36px;
}
.stat-tile {
  background: var(--surface-1);
  padding: 18px 20px;
}
.stat-label {
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}
.stat-value {
  font-size: 26px;
  font-weight: 600;
  color: var(--text-primary);
}
.stat-sub {
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 4px;
}
h2 {
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin: 0 0 14px;
}
.gantt {
  margin-bottom: 36px;
}
.legend {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.legend-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}
.gantt-body {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 0;
}
.gantt-row {
  display: grid;
  grid-template-columns: 220px 1fr;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--gridline);
}
.gantt-row:last-child { border-bottom: none; }
.gantt-label {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}
.gantt-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.gantt-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gantt-harness {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}
.gantt-track {
  position: relative;
  height: 24px;
  background: var(--surface-2);
  border-radius: 4px;
}
.gantt-bar {
  position: absolute;
  top: 2px;
  bottom: 2px;
  border-radius: 4px;
  min-width: 6px;
}
.pr-badge {
  position: absolute;
  top: 50%;
  right: -4px;
  transform: translate(100%, -50%);
  border: 1px solid;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 10px;
  white-space: nowrap;
  background: var(--surface-1);
}
.gantt-axis {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  padding: 0 16px;
  font-size: 11px;
  color: var(--muted);
}
.events { margin-bottom: 8px; }
.event-list {
  list-style: none;
  margin: 0;
  padding: 0;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.event-row {
  display: grid;
  grid-template-columns: 20px 76px 140px 1fr;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--gridline);
  font-size: 13px;
}
.event-row:last-child { border-bottom: none; }
.event-icon { font-size: 13px; text-align: center; }
.event-time {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.event-type {
  color: var(--text-secondary);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.event-label { color: var(--text-primary); }
.empty { color: var(--muted); font-size: 13px; }
"""


def render_html(recap):
    project = recap.get("project") or {}
    stats = recap.get("stats") or {}
    sessions = recap.get("sessions") or []
    timeline = recap.get("timeline") or []

    project_name = project.get("name") or project.get("id") or "AO Replay"
    generated_at = recap.get("generated_at")
    timestamp_html = (
        f'<div class="timestamp">Generated {_e(_fmt_dt(generated_at))}</div>'
        if generated_at
        else ""
    )

    agent_count = stats.get("agent_count", 0) or 0
    wall_clock = _fmt_duration(stats.get("wall_clock_seconds", 0))
    time_saved_pct = stats.get("time_saved_pct", 0) or 0
    subtitle = f"{agent_count} agents · {wall_clock} wall clock · {time_saved_pct:.1f}% time saved"

    harness_colors = _harness_colors(sessions)

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(project_name)} — Replay</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="viz-root">
  <header>
    {timestamp_html}
    <h1>{_e(project_name)}</h1>
    <div class="subtitle">{_e(subtitle)}</div>
  </header>
  {_render_stats(stats)}
  {_render_timeline(recap, harness_colors)}
  {_render_events(timeline)}
</div>
</body>
</html>"""
    return body
