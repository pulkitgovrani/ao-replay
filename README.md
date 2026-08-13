# AO Replay

AO Replay turns an Agent Orchestrator session's local SQLite history into a
shareable recap: a self-contained HTML page with stats on how many agents
ran in parallel, time saved versus doing the work sequentially, PR/CI
outcomes, and a timeline — plus a deterministic narration script you can
read aloud over a screen recording of that page.

## Quick start

```sh
git clone <this-repo>
cd ao-replay
./bin/ao-replay report --demo
open ao-replay-recap.html   # or just open the file in a browser
```

This uses the bundled demo fixture, so it works immediately with zero
install steps.

## Real usage

```sh
./bin/ao-replay report
```

With no `--demo` flag, `ao-replay` reads directly from your local AO
database at `~/.ao/data/ao.db`, read-only. Pass `--db PATH` to point at a
different database, or `--project ID` to scope to a specific project.
Output paths default to `ao-replay-recap.html` and `ao-replay-script.txt`,
and can be overridden with `--out` / `--script-out`.

## Built with Agent Orchestrator

This project was itself built using Agent Orchestrator: three parallel
`claude-code` worker sessions — ingest, render, and cli+narration — worked
against a shared JSON contract (`ao_replay/fixtures/demo_recap.json`) and
were merged in via AO-managed PRs. It was built for **The Orchestra**
hackathon.

## Dependencies

Zero runtime dependencies — Python 3 standard library only.

## Privacy

AO Replay only ever reads your local `~/.ao` SQLite file, read-only.
Nothing leaves your machine.
