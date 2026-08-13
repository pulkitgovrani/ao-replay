import json
import os
import unittest

from ao_replay.render import render_html

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "demo_recap.json"
)


class TestRenderHtml(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE_PATH) as f:
            self.recap = json.load(f)
        self.html = render_html(self.recap)

    def test_starts_with_doctype_or_html_tag(self):
        prefix = self.html.lstrip()[:15].lower()
        self.assertTrue(
            prefix.startswith("<!doctype html") or prefix.startswith("<html"),
            f"unexpected start: {prefix!r}",
        )

    def test_no_external_resource_references(self):
        self.assertNotIn('<script src="http', self.html)
        self.assertNotIn('<link href="http', self.html)
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)

    def test_contains_each_session_display_name(self):
        for session in self.recap["sessions"]:
            self.assertIn(session["display_name"], self.html)

    def test_contains_project_name_and_is_str(self):
        self.assertIsInstance(self.html, str)
        self.assertIn(self.recap["project"]["name"], self.html)


if __name__ == "__main__":
    unittest.main()
