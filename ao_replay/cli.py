"""Command-line entry point for AO Replay.

    ao-replay report [--db PATH] [--project ID] [--demo] [--out FILE.html] [--script-out FILE.txt]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ao_replay.ingest import load_recap
from ao_replay.render import render_html
from ao_replay.narrate import generate_script

DEFAULT_DB_PATH = Path.home() / ".ao" / "data" / "ao.db"
DEFAULT_OUT = "ao-replay-recap.html"
DEFAULT_SCRIPT_OUT = "ao-replay-script.txt"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ao-replay")
    subparsers = parser.add_subparsers(dest="command", required=True)

    report = subparsers.add_parser(
        "report", help="Generate a recap HTML page and narration script"
    )
    report.add_argument(
        "--db", default=None, help="Path to the AO SQLite db (default: ~/.ao/data/ao.db)"
    )
    report.add_argument(
        "--project", dest="project_id", default=None, help="Project ID to filter by"
    )
    report.add_argument(
        "--demo", action="store_true", help="Use the bundled demo fixture instead of a real db"
    )
    report.add_argument("--out", default=DEFAULT_OUT, help="Path to write the recap HTML")
    report.add_argument(
        "--script-out", default=DEFAULT_SCRIPT_OUT, help="Path to write the narration script"
    )

    return parser


def _run_report(args: argparse.Namespace) -> int:
    if not args.demo and args.db is None and not DEFAULT_DB_PATH.exists():
        print(
            f"error: no AO database found at {DEFAULT_DB_PATH} and --demo was not passed.\n"
            "Try: ao-replay report --demo",
            file=sys.stderr,
        )
        return 1

    try:
        recap = load_recap(db_path=args.db, project_id=args.project_id, demo=args.demo)
    except Exception as exc:  # noqa: BLE001 - surface any failure as a clean CLI error
        print(f"error: failed to load recap data: {exc}", file=sys.stderr)
        return 1

    try:
        html = render_html(recap)
        script = generate_script(recap)
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to generate recap: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    script_path = Path(args.script_out)

    try:
        out_path.write_text(html, encoding="utf-8")
        script_path.write_text(script, encoding="utf-8")
    except OSError as exc:
        print(f"error: failed to write output files: {exc}", file=sys.stderr)
        return 1

    stats = recap.get("stats", {})
    project_name = recap.get("project", {}).get("name", "unknown project")

    print(f"Project: {project_name}")
    print(f"Agents: {stats.get('agent_count', 0)}")
    print(f"Time saved: {stats.get('time_saved_pct', 0)}%")
    print(f"PRs merged: {stats.get('prs_merged', 0)}/{stats.get('prs_opened', 0)}")
    print(f"Recap HTML: {out_path}")
    print(f"Narration script: {script_path}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "report":
        return _run_report(args)

    parser.error(f"unknown command: {args.command}")
    return 2


def entry_point() -> None:
    sys.exit(main())


if __name__ == "__main__":
    entry_point()
