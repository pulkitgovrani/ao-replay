import json
import unittest
from pathlib import Path

from ao_replay.narrate import generate_script

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "demo_recap.json"


class TestGenerateScript(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            self.recap = json.load(f)

    def test_returns_non_empty_string(self):
        script = generate_script(self.recap)
        self.assertIsInstance(script, str)
        self.assertTrue(script.strip())

    def test_contains_every_session_display_name(self):
        script = generate_script(self.recap)
        for session in self.recap["sessions"]:
            self.assertIn(session["display_name"], script)

    def test_contains_time_saved_pct(self):
        script = generate_script(self.recap)
        pct = self.recap["stats"]["time_saved_pct"]
        self.assertIn(str(pct), script)

    def test_timestamps_are_monotonically_increasing(self):
        script = generate_script(self.recap)
        timestamps = []
        for line in script.splitlines():
            self.assertTrue(line.startswith("["))
            close = line.index("]")
            minutes, seconds = line[1:close].split(":")
            timestamps.append(int(minutes) * 60 + int(seconds))
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertEqual(len(timestamps), len(set(timestamps)))


if __name__ == "__main__":
    unittest.main()
