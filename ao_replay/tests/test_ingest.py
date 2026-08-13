import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ao_replay.ingest import FIXTURE_PATH, load_recap


def _create_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            path TEXT,
            display_name TEXT
        );
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            num INTEGER,
            kind TEXT,
            harness TEXT,
            activity_state TEXT,
            activity_last_at TEXT,
            is_terminated INTEGER,
            branch TEXT,
            created_at TEXT,
            updated_at TEXT,
            display_name TEXT
        );
        CREATE TABLE pr (
            url TEXT PRIMARY KEY,
            session_id TEXT,
            number INTEGER,
            pr_state TEXT,
            ci_state TEXT,
            review_decision TEXT,
            mergeability TEXT,
            additions INTEGER,
            deletions INTEGER,
            changed_files INTEGER,
            updated_at TEXT,
            created_at_provider TEXT,
            merged_at_provider TEXT
        );
        CREATE TABLE pr_checks (
            pr_url TEXT,
            name TEXT,
            commit_hash TEXT,
            status TEXT,
            created_at TEXT
        );
        CREATE TABLE change_log (
            seq INTEGER PRIMARY KEY,
            project_id TEXT,
            session_id TEXT,
            event_type TEXT,
            payload TEXT,
            created_at TEXT
        );
        """
    )

    conn.execute(
        "INSERT INTO projects (id, path, display_name) VALUES (?, ?, ?)",
        ("proj1", "/tmp/proj1", "Proj One"),
    )

    # Two sessions that start at the same time but run for different
    # durations, so they overlap: this exercises wall_clock vs. the
    # cumulative sum of per-session durations (i.e. "time saved").
    conn.execute(
        """
        INSERT INTO sessions
            (id, project_id, num, kind, harness, activity_state, activity_last_at,
             is_terminated, branch, created_at, updated_at, display_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "s1", "proj1", 1, "worker", "claude-code", "idle", None,
            1, "ao/s1/root", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", "sess-one",
        ),
    )
    conn.execute(
        """
        INSERT INTO sessions
            (id, project_id, num, kind, harness, activity_state, activity_last_at,
             is_terminated, branch, created_at, updated_at, display_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "s2", "proj1", 2, "worker", "claude-code", "idle", None,
            1, "ao/s2/root", "2026-01-01T00:00:00Z", "2026-01-01T02:00:00Z", "sess-two",
        ),
    )

    conn.execute(
        """
        INSERT INTO pr
            (url, session_id, number, pr_state, ci_state, review_decision,
             mergeability, additions, deletions, changed_files, updated_at,
             created_at_provider, merged_at_provider)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "u1", "s1", 1, "merged", "passing", "approved", "mergeable",
            10, 2, 3, "2026-01-01T01:00:00Z", "2026-01-01T00:10:00Z", "2026-01-01T01:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO pr
            (url, session_id, number, pr_state, ci_state, review_decision,
             mergeability, additions, deletions, changed_files, updated_at,
             created_at_provider, merged_at_provider)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "u2", "s2", 2, "open", "pending", None, "unknown",
            5, 1, 2, "2026-01-01T02:00:00Z", "2026-01-01T00:20:00Z", None,
        ),
    )

    conn.executemany(
        "INSERT INTO pr_checks (pr_url, name, commit_hash, status, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            ("u1", "ci", "abc", "passed", "2026-01-01T00:50:00Z"),
            ("u1", "lint", "abc", "passed", "2026-01-01T00:55:00Z"),
            ("u2", "ci", "def", "failed", "2026-01-01T01:50:00Z"),
            ("u2", "ci", "def", "passed", "2026-01-01T01:55:00Z"),
        ],
    )

    conn.executemany(
        "INSERT INTO change_log (project_id, session_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            ("proj1", "s1", "session_created", json.dumps({"display_name": "sess-one", "harness": "claude-code"}), "2026-01-01T00:00:00Z"),
            ("proj1", "s2", "session_created", json.dumps({"display_name": "sess-two", "harness": "claude-code"}), "2026-01-01T00:00:01Z"),
            ("proj1", "s1", "pr_created", json.dumps({"number": 1, "title": "Add feature"}), "2026-01-01T00:10:00Z"),
            ("proj1", "s1", "pr_check_recorded", json.dumps({"number": 1, "status": "passed", "name": "ci"}), "2026-01-01T00:50:00Z"),
            ("proj1", "s1", "pr_updated", json.dumps({"number": 1, "state": "merged"}), "2026-01-01T01:00:00Z"),
        ],
    )

    conn.commit()
    conn.close()


class TestLoadRecapDemo(unittest.TestCase):
    def test_demo_returns_fixture_unchanged(self):
        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            expected = json.load(f)
        self.assertEqual(load_recap(demo=True), expected)


class TestLoadRecapFromDb(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "ao.db")
        _create_db(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_stats_computed_from_db(self):
        recap = load_recap(db_path=self.db_path)

        self.assertEqual(recap["project"], {"id": "proj1", "name": "Proj One"})
        self.assertEqual(len(recap["sessions"]), 2)

        stats = recap["stats"]
        # s1 ran 1h, s2 ran 2h, both starting at the same instant:
        # wall clock = 2h, cumulative = 3h, so 1h (3600s) was "saved".
        self.assertAlmostEqual(stats["wall_clock_seconds"], 7200.0)
        self.assertAlmostEqual(stats["cumulative_agent_seconds"], 10800.0)
        self.assertAlmostEqual(stats["time_saved_seconds"], 3600.0)
        self.assertAlmostEqual(stats["time_saved_pct"], 33.3)

        self.assertEqual(stats["sessions_total"], 2)
        self.assertEqual(stats["agent_count"], 2)
        self.assertEqual(stats["harnesses"], {"claude-code": 2})

        self.assertEqual(stats["prs_opened"], 2)
        self.assertEqual(stats["prs_merged"], 1)
        self.assertEqual(stats["additions"], 15)
        self.assertEqual(stats["deletions"], 3)
        self.assertEqual(stats["files_changed"], 5)

        self.assertEqual(stats["ci_checks_passed"], 3)
        self.assertEqual(stats["ci_checks_failed"], 1)

        self.assertEqual(stats["tokens_total"], 0)
        self.assertIsNone(stats["cost_usd"])

        s1 = next(s for s in recap["sessions"] if s["id"] == "s1")
        self.assertEqual(s1["pr"], {"number": 1, "state": "merged", "ci_state": "passing", "additions": 10, "deletions": 2})
        self.assertTrue(s1["is_terminated"])
        self.assertEqual(s1["ended_at"], "2026-01-01T01:00:00Z")

        self.assertEqual(len(recap["timeline"]), 5)
        self.assertEqual(recap["timeline"][0]["type"], "session_created")
        self.assertEqual(recap["timeline"][-1]["type"], "pr_updated")
        for event in recap["timeline"]:
            self.assertTrue(event["label"])

    def test_missing_db_path_falls_back_to_demo(self):
        missing_path = os.path.join(self.tmpdir.name, "does_not_exist.db")
        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            expected = json.load(f)
        self.assertEqual(load_recap(db_path=missing_path), expected)

    def test_empty_database_returns_zeros_gracefully(self):
        empty_db_path = os.path.join(self.tmpdir.name, "empty.db")
        conn = sqlite3.connect(empty_db_path)
        conn.executescript(
            """
            CREATE TABLE projects (id TEXT PRIMARY KEY, path TEXT, display_name TEXT);
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, project_id TEXT, num INTEGER, kind TEXT,
                harness TEXT, activity_state TEXT, activity_last_at TEXT,
                is_terminated INTEGER, branch TEXT, created_at TEXT,
                updated_at TEXT, display_name TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO projects (id, path, display_name) VALUES (?, ?, ?)",
            ("proj-empty", "/tmp/proj-empty", "Empty Project"),
        )
        conn.commit()
        conn.close()

        recap = load_recap(db_path=empty_db_path)
        self.assertEqual(recap["sessions"], [])
        self.assertEqual(recap["timeline"], [])
        self.assertEqual(recap["stats"]["sessions_total"], 0)
        self.assertEqual(recap["stats"]["wall_clock_seconds"], 0.0)
        self.assertEqual(recap["stats"]["cumulative_agent_seconds"], 0.0)
        self.assertEqual(recap["stats"]["time_saved_seconds"], 0.0)
        self.assertEqual(recap["stats"]["time_saved_pct"], 0.0)
        self.assertEqual(recap["stats"]["ci_checks_passed"], 0)
        self.assertEqual(recap["stats"]["ci_checks_failed"], 0)


if __name__ == "__main__":
    unittest.main()
